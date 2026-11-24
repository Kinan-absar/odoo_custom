"""Real ORM regression cases for an isolated Odoo 18 test database.

The caller supplies a portal-context controller, a fixture RFQ payload and an
administrator fixture environment. The caller MUST roll back the transaction.
This is not a production maintenance script or an HTTP endpoint.
"""
from copy import deepcopy
from pathlib import Path
import importlib.util
from odoo.exceptions import AccessError, UserError
from werkzeug.exceptions import Forbidden, NotFound
from odoo.tools.convert import convert_xml_import
from lxml import etree


def check_runtime(env, service, payload):
    def call(method, data):
        service._json = lambda run: run(deepcopy(data))
        endpoint = getattr(service, method)
        return endpoint.__wrapped__(service, po_id=data['id']) if method == 'decision' else endpoint.__wrapped__(service)

    def close(actual, expected):
        assert abs(actual - expected) < 0.00001, (actual, expected)

    actor = service._actor()
    assert actor.share and not actor.has_group('base.group_user')
    preview = call('preview', payload)
    assert len(preview['lines']) == len(payload['lines']) == 5
    assert [row['product_qty'] for row in preview['lines']] == [4, 1, 34, 0, 0]
    assert [row['price_unit'] for row in preview['lines']] == [45, 45450, 3450, 0, 0]
    close(preview['untaxed'], 162930)
    close(preview['tax'], 24439.5)
    close(preview['total'], 187369.5)

    saved = call('save', payload)
    order = env['purchase.order'].browse(int(saved['url'].rsplit('/', 1)[1]))
    assert order.state == 'draft' and order.absar_portal_review_state == 'draft'
    assert order.user_id == actor
    assert len(order.order_line) == 5
    close(order.amount_total, preview['total'])
    assert order.order_line[-2:].mapped('product_qty') == [0.0, 0.0]

    # Edit the same draft: preserve real line identifiers and exercise the
    # version/ownership guard with sections and notes still present.
    edit = deepcopy(payload)
    edit.update(id=order.id, version=str(order.write_date))
    for row, native in zip(edit['lines'], order.order_line):
        row['id'] = native.id
    edit['lines'][0].update(product_qty=5, price_unit=12.34, discount=10)
    changed_preview = call('preview', edit)
    close(changed_preview['lines'][0]['price_subtotal'], 55.53)
    call('save', edit)
    order.invalidate_recordset()
    close(order.amount_total, changed_preview['total'])
    assert len(order.order_line) == 5

    vendor = env['res.partner'].create({'name': 'Disposable changed vendor', 'supplier_rank': 1})
    edit.update(partner_id=vendor.id, version=str(order.write_date))
    vendor_preview = call('preview', edit)
    call('save', edit)
    order.invalidate_recordset()
    close(order.amount_total, vendor_preview['total'])
    close(order.order_line[0].discount, 10)

    portal_reviewer = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'Disposable Portal Approver', 'login': 'portal-runtime-approver',
        'company_id': order.company_id.id, 'company_ids': [(6, 0, [order.company_id.id])],
        'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                              env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver').id])],
    })
    env['hr.employee'].create({'name': portal_reviewer.name, 'user_id': portal_reviewer.id,
                              'company_id': order.company_id.id})
    assert portal_reviewer.share and not portal_reviewer.has_group('base.group_user')

    # Submission must keep the document an RFQ and record a separate review.
    edit.update(version=str(order.write_date), submit=True)
    call('save', edit)
    order.invalidate_recordset()
    assert order.state == 'draft' and order.absar_portal_review_state == 'submitted'

    try:
        order.with_user(actor).action_absar_portal_approve_confirm()
    except AccessError:
        pass
    else:
        raise AssertionError('Portal preparer must not approve or confirm')
    assert not actor.has_group('base.group_user')
    manager = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'Disposable Purchase Manager', 'login': 'portal-runtime-manager',
        'company_id': order.company_id.id, 'company_ids': [(6, 0, [order.company_id.id])],
        'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref('purchase.group_purchase_manager').id, env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver').id])],
    })
    assert not manager.share
    order.with_user(manager).action_absar_portal_approve_confirm()
    order.invalidate_recordset()
    assert order.state in ('purchase', 'done')
    assert order.absar_portal_review_state == 'approved' and order.absar_portal_approver_id == manager
    assert order.user_id == actor and not actor.has_group('base.group_user')

    # Load the actual inherited form/search views and internal queue action.
    # This exercises Odoo's view validator rather than only XML syntax checks.
    addon = Path(__file__).resolve().parents[1]
    with (addon / 'views/purchase_order_views.xml').open('rb') as source:
        convert_xml_import(env, 'absar_portal_purchase_monitor', source, {}, mode='update')
    arch = env['purchase.order'].with_user(manager).get_view(
        view_id=env.ref('purchase.purchase_order_form').id, view_type='form')['arch']
    document = etree.fromstring(arch.encode())
    assert document.xpath("//button[@name='action_absar_portal_approve_confirm']")
    assert document.xpath("//page[@name='absar_portal_purchase_review']")
    action = env.ref('absar_portal_purchase_monitor.action_portal_purchase_requests')
    assert action.res_model == 'purchase.order'

    legacy = env['purchase.order'].create({
        'partner_id': order.partner_id.id, 'company_id': order.company_id.id,
        'user_id': False, 'absar_portal_preparer_id': actor.id,
        'absar_portal_review_state': 'approved', 'absar_portal_approver_id': actor.id,
    })
    migration_path = addon / 'migrations/18.0.1.5.4/post-migration.py'
    spec = importlib.util.spec_from_file_location('buyer_migration', migration_path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    migration.migrate(env.cr, '18.0.1.5.3')
    legacy.invalidate_recordset()
    assert legacy.user_id == actor and legacy.absar_portal_review_state == 'submitted'
    order.invalidate_recordset()
    assert order.state in ('purchase', 'done') and order.absar_portal_approver_id == manager

    # The same Approver role authorizes a separate portal account. It must
    # retain its account type while invoking the native confirmation chain.
    portal_payload = deepcopy(payload)
    portal_payload['submit'] = True
    portal_saved = call('save', portal_payload)
    portal_order = env['purchase.order'].browse(int(portal_saved['url'].rsplit('/', 1)[1]))
    assert portal_order.state == 'draft' and portal_order.absar_portal_review_state == 'submitted'
    request = service._actor.__func__.__globals__['request']
    issuer_env = request.env
    request.env = env(user=portal_reviewer.id, context=dict(issuer_env.context))
    try:
        boot = service._boot(service._record(portal_order.id))
        assert boot['can_review'] and not boot['can_create_product']
        call('decision', {'id': portal_order.id, 'action': 'approve_confirm', 'version': str(portal_order.write_date)})
    finally:
        request.env = issuer_env
    portal_order.invalidate_recordset()
    assert portal_order.state in ('purchase', 'done')
    assert portal_order.absar_portal_approver_id == portal_reviewer
    assert portal_reviewer.share and not portal_reviewer.has_group('base.group_user')
    assert not portal_reviewer.has_group('purchase.group_purchase_user')

    # Monitor can read confirmed company orders, never draft/edit/product actions.
    monitor = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'Disposable Portal Monitor', 'login': 'portal-runtime-monitor',
        'company_id': order.company_id.id, 'company_ids': [(6, 0, [order.company_id.id])],
        'groups_id': [(6, 0, [env.ref('base.group_portal').id,
                              env.ref('absar_portal_purchase_monitor.group_portal_purchase_monitor').id])],
    })
    env['hr.employee'].create({'name': monitor.name, 'user_id': monitor.id, 'company_id': order.company_id.id})
    request.env = env(user=monitor.id, context=dict(issuer_env.context))
    try:
        assert service._record(order.id) == order
        assert service._boot(service._record(order.id))['readonly']
        for operation in (lambda: service._record(legacy.id),
                          lambda: service._record(order.id, edit=True),
                          lambda: call('product_defaults', {'company_id': payload['company_id']})):
            try:
                operation()
            except (Forbidden, NotFound, AccessError):
                pass
            else:
                raise AssertionError('Monitor must remain read only and cannot see drafts')
    finally:
        request.env = issuer_env
    # Even a user with both roles cannot approve their own submitted request.
    own_payload = deepcopy(payload); own_payload['submit'] = True
    own_saved = call('save', own_payload)
    own_order = env['purchase.order'].browse(int(own_saved['url'].rsplit('/', 1)[1]))
    actor.sudo().write({'groups_id': [(4, env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver').id)]})
    try:
        own_order.with_user(actor).sudo().action_absar_portal_approve_confirm()
    except UserError:
        pass
    else:
        raise AssertionError('Combined Issuer/Approver must not self approve')
    actor.sudo().write({'groups_id': [(3, env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver').id)]})

    # Exercise actual role consolidation twice, including aliases and memberships.
    legacy_groups = {}
    for name in ('confirmer', 'product_creator', 'native'):
        group = env['res.groups'].create({'name': 'Legacy ' + name})
        env['ir.model.data'].create({'module': 'absar_portal_purchase_monitor',
            'name': 'group_portal_purchase_' + name, 'model': 'res.groups', 'res_id': group.id})
        legacy_groups[name] = group
    legacy_groups['confirmer'].users = [(4, portal_reviewer.id)]
    legacy_groups['product_creator'].users = [(4, actor.id)]
    migration_path = addon / 'migrations/18.0.1.5.5/pre-migration.py'
    spec = importlib.util.spec_from_file_location('role_migration', migration_path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    for repeat in range(2):
        migration.migrate(env.cr, '18.0.1.5.4')
    assert env.ref('absar_portal_purchase_monitor.group_portal_purchase_confirmer') == env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver')
    assert env.ref('absar_portal_purchase_monitor.group_portal_purchase_product_creator') == env.ref('absar_portal_purchase_monitor.group_portal_purchase_preparer')
    assert not env.ref('absar_portal_purchase_monitor.group_portal_purchase_native', raise_if_not_found=False)
    assert not env['res.groups'].browse([group.id for group in legacy_groups.values()]).exists()
    assert actor.share and portal_reviewer.share and not actor.has_group('base.group_user')
    assert manager.has_group('absar_portal_purchase_monitor.group_portal_purchase_approver')
    print('PASS: portal/internal unified approval, no self approval or account conversion; legacy role migration idempotent.')

    # An internal Purchase user without an employee link issues directly in the
    # native app. Original Confirm RPC submits; no PO/receipt is created yet.
    internal_issuer = env['res.users'].with_context(no_reset_password=True).create({
        'name': 'Disposable Internal Issuer', 'login': 'internal-runtime-issuer',
        'company_id': order.company_id.id, 'company_ids': [(6, 0, [order.company_id.id])],
        'groups_id': [(6, 0, [env.ref('base.group_user').id, env.ref('purchase.group_purchase_user').id])],
    })
    assert not internal_issuer.employee_id
    spec = importlib.util.spec_from_file_location('internal_issuer_migration', addon / 'migrations/18.0.1.5.6/pre-migration.py')
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    for repeat in range(2):
        migration.migrate(env.cr, '18.0.1.5.5')
    assert internal_issuer.has_group('absar_portal_purchase_monitor.group_portal_purchase_preparer')
    assert not actor.has_group('base.group_user') and portal_reviewer.share
    native_order = env['purchase.order'].with_user(internal_issuer).create({
        'partner_id': vendor.id, 'company_id': order.company_id.id, 'user_id': internal_issuer.id,
        'order_line': [(0, 0, {'product_id': order.order_line[0].product_id.id,
            'name': 'Native internal-issued product', 'product_qty': 2, 'price_unit': 10,
            'product_uom': order.order_line[0].product_uom.id, 'date_planned': '2026-10-18 10:00:00'})],
    })
    assert not native_order.absar_portal_preparer_id
    native_order.button_confirm()
    native_order.invalidate_recordset()
    assert native_order.state == 'draft' and native_order.absar_portal_review_state == 'submitted'
    assert native_order.absar_portal_preparer_id == internal_issuer and native_order.user_id == internal_issuer
    assert not native_order.picking_ids
    assert portal_reviewer in native_order.sudo().absar_portal_reviewer_ids
    assert manager in native_order.sudo().absar_portal_reviewer_ids
    assert internal_issuer not in native_order.sudo().absar_portal_reviewer_ids
    for operation in (native_order.button_confirm, native_order.button_approve,
                      native_order.action_absar_portal_approve_confirm):
        try:
            operation()
        except (AccessError, UserError):
            pass
        else:
            raise AssertionError('Internal issuer must not bypass approval')
    # Real inherited portal bell summary: no native activity or push subscription
    # is needed to discover a pending internal-issued RFQ in the portal.
    markers = env['portal.report.seen'].sudo()
    portal_attention = markers._get_notification_summary(portal_reviewer)
    assert 'fixture_existing' in portal_attention
    pending_count = portal_attention['purchase_approval']['count']
    assert pending_count > 0 and portal_attention['purchase_approval']['new'] > 0
    assert portal_attention['purchase_approval']['url'] == '/my/employee/purchase/approvals'
    assert not markers._get_purchase_approval_summary(internal_issuer)
    assert not markers._get_purchase_approval_summary(monitor)
    assert 'purchase_approval' not in markers._get_notification_summary(actor)
    # Exercise the actual queue GET: internal-issued RFQ is in the portal list,
    # and visiting the list sets the newly registered purchase seen marker.
    from types import SimpleNamespace
    request.env = env(user=portal_reviewer.id, context=dict(issuer_env.context))
    request.httprequest = SimpleNamespace(path='/my/employee/purchase/approvals')
    request.render = lambda template, values: values
    try:
        listing = service.listing.__wrapped__(service)
        assert native_order.id in listing['orders'].ids
        assert markers._get_last_seen(portal_reviewer.id, 'purchase_approval')
        assert service._boot(service._record(native_order.id))['approvers']
    finally:
        request.env = issuer_env
    # Load the real inherited EPS home template and render its attention card.
    # A tiny outer layout replaces unrelated EPS navigation in this probe.
    layout = env['ir.ui.view'].create({'name': 'Disposable outer portal layout', 'type': 'qweb',
        'key': 'employee_portal_suite.employee_portal_layout',
        'arch_db': '<t t-name="employee_portal_suite.employee_portal_layout"><main><t t-out="0"/></main></t>'})
    env['ir.model.data'].create({'module': 'employee_portal_suite', 'name': 'employee_portal_layout',
                                  'model': 'ir.ui.view', 'res_id': layout.id})
    salary_group = env['res.groups'].create({'name': 'Disposable Salary Viewer'})
    env['ir.model.data'].create({'module': 'employee_portal_suite', 'name': 'group_salary_report_viewer',
                                  'model': 'res.groups', 'res_id': salary_group.id})
    dashboard_path = addon.parents[1] / 'inspection/eps/employee_portal_suite/views/employee_dashboard_page.xml'
    with dashboard_path.open('rb') as source:
        convert_xml_import(env, 'employee_portal_suite', source, {}, mode='update')
    with (addon / 'views/portal_purchase_attention.xml').open('rb') as source:
        convert_xml_import(env, 'absar_portal_purchase_monitor', source, {}, mode='update')
    dashboard_values = dict.fromkeys([
        'my_request_count', 'my_material_count', 'employee_pending_count', 'new_employee_pending_count',
        'material_pending_count', 'new_material_pending_count', 'can_er_approval_page', 'can_mr_approval_page',
        'pending_sign_count', 'new_pending_sign_count', 'salary_report_count', 'new_salary_report_count',
        'portal_report_count', 'new_portal_report_count', 'can_manage_portal_reports', 'contract_count',
        'ipc_count', 'variation_count', 'measurement_count', 'show_construction_cards',
        'attendance_checked_in', 'can_use_attendance'], 0)
    dashboard_values['recent_activities'] = []
    for viewer in (portal_reviewer, monitor):
        dashboard_values['request'] = SimpleNamespace(env=env(user=viewer.id, context=dict(issuer_env.context)))
        html = env['ir.qweb'].with_context(minimal_qcontext=True)._render(
            'employee_portal_suite.employee_portal_dashboard', dict(dashboard_values))
        document = etree.HTML(str(html))
        cards = document.xpath('//a[@href="/my/employee/purchase/approvals"]')
        assert bool(cards) == (viewer == portal_reviewer)
        assert bool(document.xpath('//div[@class="attention-clear"]')) == (viewer == monitor)
    print('PASS: actual portal queue GET lists internal-issued RFQ and marks seen; inherited EPS home compiles/renders attention for Approver and all-clear for Monitor.')

    # Load the actual dedicated portal templates and both directory controllers.
    # The outer EPS layout remains a bridge; list/form QWeb below is unmodified.
    import json
    for filename in ('portal_purchase_templates.xml', 'portal_workspace_pages.xml',
                     'portal_purchase_prepare.xml', 'portal_purchase_approval_list.xml'):
        with (addon / 'views' / filename).open('rb') as source:
            convert_xml_import(env, 'absar_portal_purchase_monitor', source, {}, mode='update')
    prepare_globals = service._actor.__func__.__globals__
    monitor_globals = {'__name__':'runtime_monitor', 'PortalPurchasePrepare':service.__class__,
                       'integer':prepare_globals['integer']}
    monitor_source = (addon / 'controllers/portal_purchase.py').read_text().replace(
        'from .portal_prepare import PortalPurchasePrepare, integer', '')
    exec(compile(monitor_source, 'actual_monitor_controller', 'exec'), monitor_globals)
    monitor_globals['request'] = request
    monitor_controller = monitor_globals['PortalPurchaseMonitor']()
    directory_globals = {'__name__':'runtime_directory', 'PortalPurchasePrepare':service.__class__,
                         'integer':prepare_globals['integer'], 'BASE':prepare_globals['BASE'],
                         'PREFIX':prepare_globals['PREFIX'], 'PortalPurchaseMonitor':monitor_globals['PortalPurchaseMonitor']}
    directory_source = (addon / 'controllers/portal_directory.py').read_text().replace(
        'from .portal_prepare import PortalPurchasePrepare, BASE, PREFIX, integer', '').replace(
        'from .portal_purchase import PortalPurchaseMonitor', '')
    exec(compile(directory_source, 'actual_directory_controller', 'exec'), directory_globals)
    directory_globals['request'] = request
    directory = directory_globals['PortalPurchaseDirectory']()
    request.redirect = lambda url: {'redirect':url}

    def render_view(template, values, viewer, path):
        view_request = SimpleNamespace(env=env(user=viewer.id, context=dict(issuer_env.context)),
            httprequest=SimpleNamespace(path=path), csrf_token=lambda:'disposable-test-token')
        html = env['ir.qweb'].with_context(minimal_qcontext=True)._render(
            'absar_portal_purchase_monitor.' + template, dict(values, request=view_request))
        return etree.HTML(str(html))

    for viewer, path in [(portal_reviewer, '/my/employee/purchase/approvals'),
                         (actor, '/my/employee/purchase')]:
        request.env = env(user=viewer.id, context=dict(issuer_env.context))
        request.httprequest.path = path
        values = service.listing.__wrapped__(service)
        document = render_view('purchase_prepare_list', values, viewer, path)
        assert document.xpath('//table[@class="apm-table"]')
        assert bool(document.xpath('//nav[@aria-label="Purchase workspace"]')) == (viewer == actor)
        assert bool(document.xpath('//a[@href="/my/employee/purchase/new"]')) == (viewer == actor)
        if viewer == portal_reviewer:
            assert document.xpath('//h2[text()="Purchase Approvals"]')
            assert not document.xpath('//a[@href="/my/employee/purchase/products"]')
        selected_order = native_order if viewer == portal_reviewer else own_order
        boot = service._boot(service._record(selected_order.id))
        detail = render_view('purchase_prepare_detail',
            {'boot':boot,'boot_json':json.dumps(boot),'po':service._record(selected_order.id)},
            viewer, '/my/employee/purchase/%s' % selected_order.id)
        assert detail.xpath('//*[@id="apw-root"]')
        assert bool(detail.xpath('//button[@data-action="approve_confirm"]')) == (viewer == portal_reviewer)
        assert not detail.xpath('//button[@data-action="save"]')
        if viewer == portal_reviewer:
            assert not detail.xpath('//nav[@aria-label="Purchase workspace"]')
            try:
                directory.products.__wrapped__(directory)
            except Forbidden:
                pass
            else:
                raise AssertionError('Approver must not open Products directory')
            assert directory.orders.__wrapped__(directory) == {'redirect':'/my/employee/purchase/approvals'}
    request.env = issuer_env
    values = directory.orders.__wrapped__(directory)
    document = render_view('purchase_monitor_list', values, actor, '/my/employee/purchase/orders')
    assert document.xpath('//table[@class="apm-table"]')
    assert {row['po'].absar_portal_preparer_id.id for row in values['rows']} == {actor.id}
    request.env = env(user=monitor.id, context=dict(issuer_env.context))
    values = monitor_controller.list_orders.__wrapped__(monitor_controller)
    assert order.id in [row['po'].id for row in values['rows']]
    assert render_view('purchase_monitor_list', values, monitor, '/my/employee/purchase-monitor').xpath('//table[@class="apm-table"]')
    assert monitor_controller.order_detail.__wrapped__(monitor_controller, order.id) == {
        'redirect':'/my/employee/purchase/%s?from_monitor=1' % order.id}
    monitor_form = directory.editor.__wrapped__(directory, po_id=order.id, from_monitor='1')
    assert monitor_form['boot']['readonly'] and not monitor_form['boot']['can_create_product']
    detail = render_view('purchase_prepare_detail', monitor_form, monitor, '/my/employee/purchase/%s' % order.id)
    assert detail.xpath('//*[@id="apw-root"]')
    assert detail.xpath('//*[@data-purchase-financial-summary="1"]')
    assert not detail.xpath('//a[contains(@href, "/purchase-monitor/")]')
    assert not detail.xpath('//button[@data-action="save" or @data-action="approve_confirm" or @data-action="confirm"]')
    request.env = issuer_env
    print('PASS: actual Issuer/Approver/Monitor list and shared-form QWeb rendering, role-specific navigation/actions, product restriction, own-order scope and Monitor redirect/read-only form.')

    # Other-company and self-issued fixtures must never inflate the count.
    other_company = env['res.company'].create({'name': 'Disposable foreign purchase company'})
    env['stock.warehouse'].create({'name': 'Foreign purchase warehouse', 'code': 'FPO', 'company_id': other_company.id})
    excluded = env['purchase.order'].create([
        {'partner_id': vendor.id, 'company_id': other_company.id,
         'absar_portal_preparer_id': actor.id, 'absar_portal_review_state': 'submitted'},
        {'partner_id': vendor.id, 'company_id': order.company_id.id,
         'absar_portal_preparer_id': portal_reviewer.id, 'absar_portal_review_state': 'submitted'},
    ])
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count
    # Eligibility must not depend on the submitting user's active company:
    # a portal approver's employee may belong to their primary company.
    portal_reviewer.write({'company_ids': [(4, other_company.id)]})
    assert portal_reviewer in excluded[0].with_company(other_company)._portal_reviewers()
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count + 1
    portal_reviewer.write({'company_ids': [(3, other_company.id)]})
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count
    markers._mark_seen(portal_reviewer.id, 'purchase_approval')
    # Simulate opening the queue in a subsequent request, after earlier writes.
    from datetime import timedelta
    markers.search([('user_id', '=', portal_reviewer.id), ('report_type', '=', 'purchase_approval')]).write(
        {'last_seen_date': native_order.write_date + timedelta(seconds=1)})
    summary = markers._get_purchase_approval_summary(portal_reviewer)
    assert summary['count'] == pending_count and summary['new'] == 0

    # Return from the portal, correct in native Purchase and resubmit.
    request.env = env(user=portal_reviewer.id, context=dict(issuer_env.context))
    try:
        call('decision', {'id': native_order.id, 'action': 'return',
                          'note': 'Correct the unit price', 'version': str(native_order.write_date)})
    finally:
        request.env = issuer_env
    native_order.invalidate_recordset()
    assert native_order.state == 'draft' and native_order.absar_portal_review_state == 'returned'
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count - 1
    native_order.order_line[0].write({'price_unit': 12})
    native_order.button_confirm()
    native_order.invalidate_recordset()
    assert native_order.absar_portal_review_state == 'submitted' and not native_order.picking_ids
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count
    # It appears in the same queue, and a portal Approver can approve it.
    assert native_order.sudo().filtered_domain(action.domain and __import__('ast').literal_eval(action.domain))
    request.env = env(user=portal_reviewer.id, context=dict(issuer_env.context))
    try:
        assert service._record(native_order.id).absar_portal_preparer_id == internal_issuer
        call('decision', {'id': native_order.id, 'action': 'approve_confirm', 'version': str(native_order.write_date)})
    finally:
        request.env = issuer_env
    native_order.invalidate_recordset()
    assert native_order.state in ('purchase', 'done')
    assert native_order.absar_portal_approver_id == portal_reviewer
    assert native_order.user_id == internal_issuer and portal_reviewer.share
    assert markers._get_purchase_approval_summary(portal_reviewer)['count'] == pending_count - 1
    print('PASS: portal approval bell/home summary includes internal requests, scopes company/role/self, acknowledges seen separately from pending, and updates on return/resubmit/confirmation.')
    native_arch = env['purchase.order'].with_user(internal_issuer).get_view(
        view_id=env.ref('purchase.purchase_order_form').id, view_type='form')['arch']
    native_document = etree.fromstring(native_arch.encode())
    assert native_document.xpath("//button[@name='button_confirm'][@string='Submit for Approval']")
    print('PASS: internal native creation -> original Confirm RPC submits only -> shared portal queue -> return/correct/resubmit -> independent portal approval confirms; internal issuer bypass denied; issuer migration idempotent.')


    # Distinguish Odoo's native threshold approval from a Studio button rule.
    company = order.company_id
    old_validation = company.po_double_validation
    old_threshold = company.po_double_validation_amount
    try:
        company.write({'po_double_validation':'two_step', 'po_double_validation_amount':0})
        extra = deepcopy(payload); extra['submit'] = True
        saved = call('save', extra)
        threshold_order = env['purchase.order'].browse(int(saved['url'].rsplit('/',1)[1]))
        threshold_order.with_user(portal_reviewer).sudo().action_absar_portal_approve_confirm()
        threshold_order.invalidate_recordset()
        assert threshold_order.absar_portal_review_state == 'approved'
        assert threshold_order.state == 'to approve' and not threshold_order.picking_ids
        threshold_order.with_user(manager).button_approve()
        threshold_order.invalidate_recordset()
        assert threshold_order.state in ('purchase','done')
        company.write({'po_double_validation':'one_step'})
        saved = call('save', extra)
        one_step_order = env['purchase.order'].browse(int(saved['url'].rsplit('/',1)[1]))
        one_step_order.with_user(portal_reviewer).sudo().action_absar_portal_approve_confirm()
        one_step_order.invalidate_recordset()
        assert one_step_order.state in ('purchase','done')
    finally:
        company.write({'po_double_validation':old_validation, 'po_double_validation_amount':old_threshold})
    print('PASS: native two-step threshold leaves portal approval To Approve until manager acts; native one-step confirms with portal Approver. No Studio rule is involved in this probe.')

    defaults = call('product_defaults', {'company_id': payload['company_id']})
    for key in ('categ_id', 'uom_id', 'uom_po_id'):
        assert isinstance(defaults[key]['id'], int) and defaults[key]['id'] > 0
    product_data = {
        'company_id': payload['company_id'], 'name': 'Disposable portal runtime product',
        'type': 'consu', 'standard_price': 8.75, 'purchase_method': 'receive',
        'supplier_taxes_id': list(payload['lines'][0]['taxes_id']),
        **{key: defaults[key]['id'] for key in ('categ_id', 'uom_id', 'uom_po_id')},
    }
    created = call('create_product', product_data)
    product = env['product.product'].browse(created['id'])
    assert product.purchase_ok and product.company_id.id == payload['company_id']
    close(product.standard_price, 8.75)
    new_line = deepcopy(payload['lines'][0])
    new_line.update(product_id=product.id, product_qty=2, product_uom=product.uom_po_id.id)
    new_payload = {**payload, 'lines': [new_line], 'defaults': True}
    product_preview = call('preview', new_payload)
    assert len(product_preview['lines']) == 1
    close(product_preview['lines'][0]['product_qty'], 2)
    close(product_preview['lines'][0]['price_unit'], 8.75)
    print('PASS: real Odoo ORM preview/totals, draft create/edit, submission request, issuer confirmation denied, unified portal/internal approve/confirm, buyer identity, native view/action loading, buyer migration and product defaults/create/add.')
