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
