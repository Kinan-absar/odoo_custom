import json
import math
import logging
import uuid
from datetime import datetime
from urllib.parse import urlencode
import pytz
from markupsafe import Markup
from werkzeug.exceptions import Forbidden, NotFound, HTTPException
from odoo import fields, http, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request
from odoo.osv import expression

BASE = '/my/employee/purchase'
PREFIX = 'absar_portal_purchase_monitor.'
_logger = logging.getLogger(__name__)


def integer(value, default=0):
    try:
        if value is True or (isinstance(value, float) and not value.is_integer()):
            raise ValueError()
        value = int(value or default)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(_('Invalid record identifier.'))
    if value < 0:
        raise ValidationError(_('Invalid record identifier.'))
    return value


def number(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(_('Invalid number: %s') % label)
    if not math.isfinite(value):
        raise ValidationError(_('Invalid number: %s') % label)
    return value


class PortalPurchasePrepare(http.Controller):
    """No generic model RPC. Every elevated access is scoped and serialized here.

    Portal groups intentionally do not imply backend ACLs on purchase, accounting,
    HR or products. Private helpers cannot be invoked through Odoo model RPC.
    """

    def _actor(self, role=None):
        user = request.env.user
        roles = ('preparer', 'approver', 'monitor', 'confirmer')
        if (not user.active or not user.employee_id or
                user.has_group('employee_portal_suite.group_attendance_only') or
                not any(user.has_group(PREFIX + 'group_portal_purchase_' + r)
                        for r in ((role,) if role else roles))):
            raise Forbidden()
        return user

    def _company(self, value=None):
        user = self._actor()
        company = request.env['res.company'].sudo().browse(integer(value, user.company_id.id)).exists()
        if not company or company not in user.company_ids:
            raise AccessError(_('Company is not available.'))
        return company

    def _env(self, company):
        return request.env(context=dict(request.env.context,
                                       allowed_company_ids=[company.id], force_company=company.id))

    def _record(self, po_id, edit=False):
        user = self._actor('preparer' if edit else None)
        po = request.env['purchase.order'].sudo().browse(po_id).exists()
        if not po or po.company_id not in user.company_ids:
            raise NotFound()
        owner = po.absar_portal_preparer_id == user and user.has_group(PREFIX + 'group_portal_purchase_preparer')
        reviewer = bool(po.absar_portal_preparer_id) and user.has_group(PREFIX + 'group_portal_purchase_approver')
        confirmer = bool(po.absar_portal_preparer_id) and user.has_group(PREFIX + 'group_portal_purchase_confirmer')
        monitor = po.state in ('purchase', 'done') and user.has_group(PREFIX + 'group_portal_purchase_monitor')
        if not (owner or reviewer or confirmer or monitor):
            raise NotFound()
        if edit and not po._portal_editable(user):
            raise AccessError(_('This RFQ is not an editable draft belonging to you.'))
        return po.with_company(po.company_id)

    def _scope(self, model, company):
        env = self._env(company)
        models = {
            'vendor': ('res.partner', [('active', '=', True), ('supplier_rank', '>', 0)], 'name'),
            'product': ('product.product', [('active', '=', True), ('purchase_ok', '=', True)], 'name'),
            'project': ('project.project', [('active', '=', True)], 'name'),
            'analytic': ('account.analytic.account', [('active', '=', True)], 'name'),
            'account': ('account.account', [('deprecated', '=', False),
                ('account_type', 'in', ['expense', 'expense_direct_cost', 'expense_depreciation', 'asset_fixed', 'asset_current'])], 'code'),
            'buyer': ('res.users', [('active', '=', True), ('share', '=', False), ('company_ids', 'in', [company.id])], 'name'),
            'currency': ('res.currency', [('active', '=', True)], 'name'),
            'tax': ('account.tax', [('active', '=', True), ('type_tax_use', '=', 'purchase')], 'sequence,id'),
            'payment_term': ('account.payment.term', [('active', '=', True)], 'name'),
            'fiscal_position': ('account.fiscal.position', [('active', '=', True)], 'name'),
            'incoterm': ('account.incoterms', [], 'code'),
            'uom': ('uom.uom', [('active', '=', True)], 'name'),
            'category': ('product.category', [], 'complete_name'),
            'picking_type': ('stock.picking.type', [('active', '=', True), ('code', '=', 'incoming')], 'name'),
            'mr': ('material.request', [('state', '=', 'approved'), ('no_po_required', '=', False)], 'id desc'),
        }
        if model not in models:
            raise ValidationError(_('Unsupported lookup.'))
        name, domain, order = models[model]
        records = env[name].sudo().with_company(company)
        if name == 'account.account':
            domain += [('company_ids', 'in', [company.id])]
        elif 'company_id' in records._fields:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        if model == 'mr':
            domain += ['|', ('project_id.company_id', '=', company.id), '&', ('project_id.company_id', '=', False), ('employee_id.company_id', '=', company.id)]
        return records, domain, order

    def _choice(self, kind, value, company, required=False):
        try:
            ident = integer(value)
        except ValidationError:
            raise ValidationError(_('Invalid identifier for %s. Select a value from the list.') % kind)
        if not ident and not required:
            model, domain, sort_order = self._scope(kind, company)
            return model.browse()
        model, domain, sort_order = self._scope(kind, company)
        record = model.search(expression.AND([domain, [('id', '=', ident)]]), limit=1)
        if not record:
            raise ValidationError(_('Invalid or unavailable %s selection.') % kind)
        return record

    def _utc(self, value):
        if not value:
            return False
        try:
            local = datetime.fromisoformat(value)
            if local.tzinfo:
                raise ValueError()
            zone = pytz.timezone(request.env.user.tz or 'UTC')
            return zone.localize(local, is_dst=None).astimezone(pytz.UTC).replace(tzinfo=None)
        except (ValueError, TypeError, pytz.AmbiguousTimeError, pytz.NonExistentTimeError, pytz.UnknownTimeZoneError):
            raise ValidationError(_('Invalid date/time. Use your user timezone.'))

    def _local(self, value):
        if not value:
            return ''
        return pytz.UTC.localize(fields.Datetime.to_datetime(value)).astimezone(
            pytz.timezone(request.env.user.tz or 'UTC')).strftime('%Y-%m-%dT%H:%M:%S')

    def _header(self, data, company):
        vendor = self._choice('vendor', data.get('partner_id'), company, True)
        currency = self._choice('currency', data.get('currency_id'), company, True)
        project = self._choice('project', data.get('project_id'), company)
        mr = self._choice('mr', data.get('material_request_id'), company)
        if mr and mr.project_id != project:
            raise ValidationError(_('Material Request must belong to the selected project.'))
        model = self._env(company)['purchase.order'].sudo().with_company(company)
        if project and 'project_id' not in model._fields:
            raise ValidationError(_('The backend project integration addon must be installed first.'))
        vals = dict(partner_id=vendor.id, partner_ref=str(data.get('partner_ref') or '')[:200],
                    company_id=company.id, currency_id=currency.id,
                    date_order=self._utc(data.get('date_order')) or fields.Datetime.now(),
                    origin=str(data.get('origin') or '')[:200],
                    material_request_id=mr.id or False)
        # Preserve plain text safely inside native HTML terms.
        vals['notes'] = str(Markup('<div style="white-space:pre-wrap">%s</div>') % str(data.get('notes') or '')[:20000])
        if 'project_id' in model._fields:
            vals['project_id'] = project.id or False
        for kind, field in [('buyer', 'user_id'), ('payment_term', 'payment_term_id'),
                            ('fiscal_position', 'fiscal_position_id'), ('incoterm', 'incoterm_id'),
                            ('picking_type', 'picking_type_id')]:
            if field in model._fields:
                vals[field] = self._choice(kind, data.get(field), company, field == 'picking_type_id').id or False
        vals['incoterm_location'] = str(data.get('incoterm_location') or '')[:200]
        return vals

    def _analytic(self, raw, company):
        if not isinstance(raw, dict) or len(raw) > 100:
            raise ValidationError(_('Invalid analytic distribution.'))
        result, totals = {}, {}
        seen_combinations = set()
        for key, raw_percent in raw.items():
            try:
                ids = [int(v) for v in str(key).split(',')]
            except ValueError:
                raise ValidationError(_('Invalid analytic account.'))
            if not ids or len(ids) > 20 or any(i <= 0 for i in ids) or len(ids) != len(set(ids)):
                raise ValidationError(_('Invalid analytic combination.'))
            accounts = [self._choice('analytic', ident, company, True) for ident in ids]
            plans = [account.plan_id.root_id.id for account in accounts]
            if len(plans) != len(set(plans)):
                raise ValidationError(_('Use one analytic account per plan in each allocation row.'))
            pct = number(raw_percent, _('Analytic percentage'))
            if not 0 < pct <= 100:
                raise ValidationError(_('Analytic percentages must be greater than zero and at most 100.'))
            canonical = ','.join(str(i) for i in sorted(ids))
            if canonical in seen_combinations:
                raise ValidationError(_('Duplicate analytic allocation.'))
            seen_combinations.add(canonical)
            result[canonical] = pct
            for plan in plans:
                totals[plan] = totals.get(plan, 0) + pct
        if any(abs(total - 100) > 0.01 for total in totals.values()):
            raise ValidationError(_('Each used analytic plan must total 100%.'))
        return result

    def _native_order(self, company, values):
        Model = self._env(company)['purchase.order'].sudo().with_company(company)
        defaults = Model.default_get(['company_id', 'state', 'date_order', 'user_id',
                                      'picking_type_id', 'notes'])
        defaults.update(company_id=company.id, partner_id=values.get('partner_id'))
        order = Model.new(defaults)
        # Execute registered native/custom partner onchanges as the form does.
        for onchange in order._onchange_methods.get('partner_id', ()):
            onchange(order)
        order.update(values)  # Explicit editor values win over vendor defaults.
        return order

    def _line(self, data, order, defaults=False):
        if not isinstance(data, dict):
            raise ValidationError(_('Invalid order line.'))
        company = order.company_id
        display = data.get('display_type') or False
        if display:
            if display not in ('line_section', 'line_note'):
                raise ValidationError(_('Invalid row type.'))
            return {'display_type': display, 'name': str(data.get('name') or '')[:4000] or _('Untitled')}
        product = self._choice('product', data.get('product_id'), company, True)
        qty = number(data.get('product_qty', 1), _('Quantity'))
        if qty <= 0:
            raise ValidationError(_('Quantity must be greater than zero.'))
        uom = self._choice('uom', data.get('product_uom') or product.uom_po_id.id, company, True)
        if uom.category_id != product.uom_id.category_id:
            raise ValidationError(_('Unit of measure must match the product category.'))
        Line = self._env(company)['purchase.order.line'].sudo().with_company(company)
        seed = {'order_id': order, 'product_id': product.id, 'product_qty': qty, 'product_uom': uom.id}
        seed.update(Line.default_get(['display_type']))
        native = Line.new(seed)
        for onchange in native._onchange_methods.get('product_id', ()):
            onchange(native)
        native.update({'product_qty': qty, 'product_uom': uom.id})
        for name in ('product_qty', 'product_uom'):
            for onchange in native._onchange_methods.get(name, ()):
                onchange(native)
        # Computed native purchase fields select seller, lead time, UoM, taxes and price.
        vals = {'product_id': product.id, 'product_qty': qty, 'product_uom': uom.id,
                'name': native.name, 'price_unit': native.price_unit,
                'date_planned': native.date_planned or order.date_order,
                'taxes_id': [(6, 0, native.taxes_id._origin.ids)],
                'analytic_distribution': native.analytic_distribution or {}}
        if 'discount' in Line._fields:
            vals['discount'] = native.discount
        if not defaults:
            vals['name'] = str(data.get('name') or native.name)[:4000]
            vals['price_unit'] = number(data.get('price_unit', native.price_unit), _('Price'))
            if vals['price_unit'] < 0:
                raise ValidationError(_('Unit price cannot be negative.'))
            vals['date_planned'] = self._utc(data.get('date_planned')) or vals['date_planned']
            tax_ids = data.get('taxes_id', [])
            if not isinstance(tax_ids, list) or len(tax_ids) > 50:
                raise ValidationError(_('Invalid purchase taxes.'))
            taxes = [self._choice('tax', v, company, True).id for v in tax_ids]
            vals['taxes_id'] = [(6, 0, list(set(taxes)))]
            vals['analytic_distribution'] = self._analytic(data.get('analytic_distribution') or {}, company)
            if 'discount' in Line._fields:
                discount = number(data.get('discount', 0), _('Discount'))
                if not 0 <= discount <= 100:
                    raise ValidationError(_('Discount must be between 0 and 100.'))
                vals['discount'] = discount
        account = self._choice('account', data.get('absar_expense_account_id'), company)
        vals['absar_expense_account_id'] = account.id or False
        return vals

    def _json(self, fn):
        try:
            with request.env.cr.savepoint():
                raw = request.params.get('payload') or '{}'
                if len(raw) > 2_000_000:
                    raise ValidationError(_('This RFQ is too large. Maximum request size is 2 MB.'))
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValidationError(_('Invalid request.'))
                return request.make_json_response(fn(data))
        except (AccessError, UserError, ValidationError, ValueError, TypeError, KeyError) as exc:
            return request.make_json_response({'error': str(exc)}, status=400)
        except HTTPException as exc:
            return request.make_json_response({'error': _('This operation is not available to your account. Reload and check your purchase role.')}, status=exc.code)
        except Exception:
            reference = uuid.uuid4().hex[:12]
            _logger.exception('Portal purchase failure %s on %s', reference, request.httprequest.path)
            return request.make_json_response({'error': _('The operation failed and was rolled back. Server log reference: %s') % reference}, status=500)

    @http.route([BASE, BASE + '/approvals', BASE + '/confirmations'], type='http', auth='user', website=True)
    def listing(self, **kw):
        confirmations = request.httprequest.path.endswith('/confirmations')
        approval = request.httprequest.path.endswith('/approvals')
        user = self._actor('confirmer' if confirmations else 'approver' if approval else 'preparer')
        domain = [('company_id', 'in', user.company_ids.ids)]
        if confirmations:
            domain += [('absar_portal_preparer_id', '!=', False), ('state', 'in', ['draft', 'sent'])]
        elif approval:
            domain += [('absar_portal_preparer_id', '!=', False), ('absar_portal_preparer_id', '!=', user.id)]
        else:
            domain += [('absar_portal_preparer_id', '=', user.id), ('state', 'not in', ['purchase', 'done'])]
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', '|', '|', ('name', 'ilike', q),
                    ('partner_id.name', 'ilike', q), ('material_request_id.name', 'ilike', q), ('origin', 'ilike', q)]])
        review = kw.get('review', 'approved' if confirmations else 'submitted' if approval else 'all')
        if review in ('draft', 'submitted', 'approved', 'returned'):
            domain += [('absar_portal_review_state', '=', review)]
        sorts = {'newest': 'id desc', 'reference': 'name asc,id desc', 'vendor': 'partner_id,id desc', 'amount': 'amount_total desc,id desc', 'date': 'date_order desc,id desc'}
        sort = kw.get('sort', 'newest')
        group_by = kw.get('group_by', '')
        group_fields = {'vendor': 'partner_id', 'buyer': 'user_id', 'company': 'company_id', 'review': 'absar_portal_review_state'}
        if 'project_id' in request.env['purchase.order']._fields:
            group_fields['project'] = 'project_id'
        group_field = group_fields.get(group_by)
        if not group_field:
            group_by = ''
        model = request.env['purchase.order'].sudo()
        count = model.search_count(domain)
        try:
            requested_page = integer(kw.get('page'), 1)
        except ValidationError:
            requested_page = 1
        page = max(1, min(requested_page, max(1, math.ceil(count / 20))))
        order = sorts.get(sort, sorts['newest'])
        if group_field:
            order = group_field + ',' + order
        orders = model.search(domain, order=order, limit=20, offset=(page - 1) * 20)
        base = BASE + ('/confirmations' if confirmations else '/approvals' if approval else '')
        page_url = lambda n: base + '?' + urlencode(dict(q=q, review=review, sort=sort, group_by=group_by, page=n))
        return request.render(PREFIX + 'purchase_prepare_list', dict(
            orders=orders, orders_only=False, group_by=group_by, group_labels={po.id: (dict(po._fields[group_field]._description_selection(po.env)).get(po[group_field], 'Not set') if group_field == 'absar_portal_review_state' else po[group_field].display_name or 'Not set') for po in orders} if group_field else {}, approval=approval, confirmations=confirmations, q=q, review=review, sort=sort,
            page=page, pages=max(1, math.ceil(count / 20)), total=count,
            previous_url=page_url(page - 1), next_url=page_url(page + 1)))

    def _boot(self, po=False, company=None):
        user = self._actor('preparer' if not po else None)
        company = po.company_id if po else company or user.company_id
        readonly = bool(po and not po._portal_editable(user))
        vals = dict(company_id=company.id, currency_id=company.currency_id.id,
                    date_order=self._local(fields.Datetime.now()), date_planned='', notes='', lines=[])
        def choice(record):
            return {'id': record._origin.id, 'label': record.display_name} if record and record._origin.id else None
        if po:
            vals.update({k: po[k] or '' for k in ['partner_ref', 'origin', 'incoterm_location']})
            vals.update(date_order=self._local(po.date_order), date_planned=self._local(po.date_planned), notes=self._plain(po.notes),
                        company_id=company.id, currency_id=po.currency_id.id)
        names = {'partner_id': 'vendor', 'project_id': 'project', 'material_request_id': 'mr',
                 'currency_id': 'currency', 'user_id': 'buyer', 'payment_term_id': 'payment_term',
                 'fiscal_position_id': 'fiscal_position', 'incoterm_id': 'incoterm', 'picking_type_id': 'picking_type'}
        selected = {}
        for field in names:
            if po and field in po._fields:
                selected[field] = choice(po[field])
            else:
                selected[field] = None
        if not po:
            selected['currency_id'] = choice(company.currency_id)
            # Do not preselect a portal user as a backend buyer.
            selected['user_id'] = choice(user) if not user.share else None
            picking = self._scope('picking_type', company)
            selected['picking_type_id'] = choice(picking[0].search(picking[1], limit=1))
        for field, selection in selected.items():
            vals[field] = selection['id'] if selection else 0
        if po:
            vals['lines'] = [self._serialize_line(line) for line in po.order_line]
        attachments = request.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'purchase.order'), ('res_id', '=', po.id), ('mimetype', '=', 'application/pdf'),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)], order='id') if po else request.env['ir.attachment'].browse()
        return dict(values=vals, selected=selected, readonly=readonly,
                    attachments=[{'id': a.id, 'name': a.name} for a in attachments],
                    totals=dict(untaxed=po.amount_untaxed, tax=po.amount_tax, total=po.amount_total, currency=po.currency_id.name) if po else None,
                    back_url=BASE if user.has_group(PREFIX + 'group_portal_purchase_preparer') else BASE + '/approvals' if user.has_group(PREFIX + 'group_portal_purchase_approver') else BASE + '/confirmations',
                    id=po.id if po else False, name=po.name if po else _('New'),
                    state=po.state if po else 'draft',
                    review=po.absar_portal_review_state if po else 'draft',
                    version=str(po.write_date) if po else '',
                    note=po.absar_portal_review_note or '' if po else '',
                    company_name=company.name, companies=[{'id': c.id, 'label': c.name, 'currency': choice(c.currency_id), 'picking_type': choice(self._scope('picking_type', c)[0].search(self._scope('picking_type', c)[1], limit=1))} for c in user.company_ids],
                    timezone=user.tz or 'UTC',
                    can_create_product=user.has_group(PREFIX + 'group_portal_purchase_product_creator') and not readonly,
                    can_review=bool(po and po.absar_portal_preparer_id and po.absar_portal_preparer_id != user and
                        user.has_group(PREFIX + 'group_portal_purchase_approver') and
                        po.state in ('draft', 'sent') and po.absar_portal_review_state in ('submitted', 'approved')),
                    can_confirm=bool(po and po.absar_portal_approver_id and
                        po.absar_portal_review_state == 'approved' and po.state in ('draft', 'sent') and
                        user.has_group(PREFIX + 'group_portal_purchase_confirmer')),
                    project_integration='project_id' in request.env['purchase.order']._fields)

    def _plain(self, value):
        from odoo.tools import html2plaintext
        return html2plaintext(value or '')

    def _serialize_line(self, line):
        analytic_labels = {}
        for key in (line.analytic_distribution or {}):
            for ident in key.split(','):
                account = request.env['account.analytic.account'].sudo().browse(int(ident)).exists()
                if account:
                    analytic_labels[ident] = {'id': account.id, 'label': account.display_name,
                                              'plan': account.plan_id.root_id.display_name}
        account = line.absar_expense_account_id
        if not account and line.product_id:
            account = line.product_id.with_company(line.company_id).property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
        return dict(id=line.id if isinstance(line.id, int) else 0,
                    display_type=line.display_type or '', name=line.name or '',
                    product_id=line.product_id._origin.id or 0, product_label=line.product_id.display_name or '',
                    product_qty=line.product_qty, product_uom=line.product_uom._origin.id or 0,
                    uom_label=line.product_uom.display_name or '', price_unit=line.price_unit,
                    discount=line.discount if 'discount' in line._fields else 0,
                    date_planned=self._local(line.date_planned),
                    taxes_id=line.taxes_id._origin.ids, taxes=[{'id': t._origin.id, 'label': t.display_name} for t in line.taxes_id if t._origin.id],
                    absar_expense_account_id=line.absar_expense_account_id._origin.id or 0,
                    account_label=line.absar_expense_account_id.display_name or '',
                    default_account=account.display_name or '',
                    analytic_distribution=line.analytic_distribution or {}, analytic_labels=analytic_labels,
                    price_subtotal=line.price_subtotal, price_total=line.price_total,
                    qty_received=line.qty_received if 'qty_received' in line._fields else 0,
                    qty_invoiced=line.qty_invoiced)

    @http.route([BASE + '/new', BASE + '/<int:po_id>'], type='http', auth='user', website=True, methods=['GET'])
    def editor(self, po_id=None, **kw):
        po = self._record(po_id) if po_id else False
        boot = self._boot(po)
        # QWeb escapes this text node. JS reads textContent, never HTML.
        return request.render(PREFIX + 'purchase_prepare_detail', dict(boot_json=json.dumps(boot), boot=boot, po=po))

    @http.route(BASE + '/lookup', type='http', auth='user', methods=['POST'], csrf=True)
    def lookup(self, **kw):
        def run(data):
            self._actor('preparer')
            company = self._company(data.get('company_id'))
            kind = data.get('kind')
            model, domain, order = self._scope(kind, company)
            q = str(data.get('q') or '')[:100]
            if q:
                name = 'name' if 'name' in model._fields else 'display_name'
                term = [(name, 'ilike', q)]
                if kind == 'product':
                    term = ['|', ('name', 'ilike', q), ('default_code', 'ilike', q)]
                elif kind == 'account':
                    term = ['|', ('name', 'ilike', q), ('code', 'ilike', q)]
                domain = expression.AND([domain, term])
            if kind == 'uom' and data.get('product_id'):
                product = self._choice('product', data['product_id'], company, True)
                domain += [('category_id', '=', product.uom_id.category_id.id)]
            offset = min(integer(data.get('offset')), 100000)
            records = model.search(domain, limit=31, offset=offset, order=order)
            return {'items': [dict(id=r.id, label=r.display_name,
                     **({'plan': r.plan_id.root_id.display_name} if kind == 'analytic' else {})) for r in records[:30]], 'more': len(records) > 30}
        return self._json(run)

    @http.route(BASE + '/preview', type='http', auth='user', methods=['POST'], csrf=True)
    def preview(self, **kw):
        def run(data):
            self._actor('preparer')
            po = self._record(integer(data['id']), edit=True) if data.get('id') else False
            company = po.company_id if po else self._company(data.get('company_id'))
            header = self._header(data, company)
            model = self._env(company)['purchase.order'].sudo().with_company(company)
            order = self._native_order(company, header)
            lines = data.get('lines') or []
            if not isinstance(lines, list) or len(lines) > 300:
                raise ValidationError(_('Maximum 300 lines per RFQ.'))
            commands, output = [], []
            for item in lines:
                vals = self._line(item, order, defaults=bool(data.get('defaults')))
                commands.append((0, 0, vals))
            order.order_line = commands
            # A new() order is a cache-only record. Recompute after attaching all
            # lines so totals cannot retain the empty-order cache populated by
            # a native/custom onchange. Use the same tax methods as Purchase.
            order.order_line._compute_amount()
            order._amount_all()
            for native in order.order_line:
                output.append(self._serialize_line(native))
            return dict(lines=output, untaxed=order.amount_untaxed, tax=order.amount_tax,
                        total=order.amount_total, currency=order.currency_id.name)
        return self._json(run)

    @http.route(BASE + '/save', type='http', auth='user', methods=['POST'], csrf=True)
    def save(self, **kw):
        def run(data):
            user = self._actor('preparer')
            po = self._record(integer(data['id']), edit=True) if data.get('id') else False
            company = po.company_id if po else self._company(data.get('company_id'))
            if po:
                po._portal_lock()
                if not po._portal_editable(user):
                    raise AccessError(_('RFQ is no longer editable.'))
                if str(po.write_date) != data.get('version'):
                    raise UserError(_('This RFQ changed since you opened it. Reload before saving.'))
            header = self._header(data, company)
            if po and integer(data.get('company_id')) != po.company_id.id:
                raise ValidationError(_('An existing RFQ cannot be moved to another company here.'))
            model = self._env(company)['purchase.order'].sudo().with_company(company)
            virtual = self._native_order(company, header)
            items = data.get('lines') or []
            if not isinstance(items, list) or len(items) > 300:
                raise ValidationError(_('Maximum 300 lines per RFQ.'))
            commands, used = [], set()
            existing = {l.id for l in po.order_line} if po else set()
            for sequence, item in enumerate(items, 1):
                vals = self._line(item, virtual)
                vals['sequence'] = sequence * 10
                ident = integer(item.get('id'))
                if ident:
                    if ident not in existing or ident in used:
                        raise AccessError(_('Order line does not belong to this RFQ.'))
                    used.add(ident)
                    commands.append((1, ident, vals))
                else:
                    commands.append((0, 0, vals))
            commands += [(2, ident, 0) for ident in existing - used]
            header.update(order_line=commands, absar_portal_review_state='draft',
                          absar_portal_approver_id=False, absar_portal_approved_on=False)
            if po:
                if str(data.get('notes') or '') == self._plain(po.notes):
                    header.pop('notes', None)  # Preserve existing rich text unless terms were edited.
                po.write(header)
            else:
                header['absar_portal_preparer_id'] = user.id
                po = model.create(header)
            if data.get('submit'):
                po._portal_submit()
            return {'url': BASE + '/%s' % po.id}
        return self._json(run)

    @http.route(BASE + '/<int:po_id>/decision', type='http', auth='user', methods=['POST'], csrf=True)
    def decision(self, po_id, **kw):
        def run(data):
            po = self._record(po_id)
            action = data.get('action')
            if action not in ('approve', 'return', 'confirm'):
                raise ValidationError(_('Unknown decision.'))
            self._actor('confirmer' if action == 'confirm' else 'approver')
            po._portal_lock()
            if str(po.write_date) != data.get('version'):
                raise UserError(_('This RFQ changed. Reload before reviewing.'))
            if action == 'return':
                if not str(data.get('note') or '').strip():
                    raise ValidationError(_('A correction note is required.'))
                po.write({'absar_portal_review_note': str(data['note'])[:2000]})
                po.action_absar_portal_return()
            elif action == 'approve':
                po.action_absar_portal_approve()
            else:
                result = po.action_absar_portal_confirm()
                if isinstance(result, dict):
                    raise UserError(_('Confirmation requires a backend wizard. Please complete it in Purchase; no changes were saved.'))
            return {'url': BASE + '/%s' % po.id}
        return self._json(run)

    @http.route(BASE + '/vendor-defaults', type='http', auth='user', methods=['POST'], csrf=True)
    def vendor_defaults(self, **kw):
        def run(data):
            self._actor('preparer')
            company = self._company(data.get('company_id'))
            vendor = self._choice('vendor', data.get('partner_id'), company, True)
            order = self._native_order(company, {'partner_id': vendor.id, 'company_id': company.id})
            choices = {}
            for name in ('currency_id', 'payment_term_id', 'fiscal_position_id'):
                record = order[name]
                choices[name] = {'id': record._origin.id, 'label': record.display_name} if record and record._origin.id else None
            return {'selected': choices, 'notes': self._plain(order.notes)}
        return self._json(run)

    @http.route(BASE + '/product-defaults', type='http', auth='user', methods=['POST'], csrf=True)
    def product_defaults(self, **kw):
        def run(data):
            self._actor('preparer')
            self._actor('product_creator')
            company = self._company(data.get('company_id'))
            Product = self._env(company)['product.product'].sudo().with_company(company)
            defaults = Product.default_get(['categ_id', 'uom_id', 'uom_po_id', 'purchase_method', 'supplier_taxes_id', 'type'])
            defaults.update(purchase_ok=True, sale_ok=False, company_id=company.id)
            product = Product.new(defaults)
            # Delegated product defaults may be pseudo-records with an origin.
            # Only real database identifiers may cross the portal boundary.
            choice = lambda r: {'id': r._origin.id, 'label': r.display_name} if r and r._origin.id else None
            return dict(categ_id=choice(product.categ_id), uom_id=choice(product.uom_id),
                        uom_po_id=choice(product.uom_po_id),
                        purchase_method=product.purchase_method,
                        supplier_taxes=[choice(t) for t in product.supplier_taxes_id if t._origin.id])
        return self._json(run)

    @http.route(BASE + '/product-create', type='http', auth='user', methods=['POST'], csrf=True)
    def create_product(self, **kw):
        def run(data):
            self._actor('preparer')
            self._actor('product_creator')
            company = self._company(data.get('company_id'))
            name = str(data.get('name') or '').strip()[:150]
            if not name:
                raise ValidationError(_('Product name is required.'))
            kind = data.get('type', 'consu')
            if kind not in ('consu', 'service'):
                raise ValidationError(_('Choose Goods or Service.'))
            category = self._choice('category', data.get('categ_id'), company, True)
            uom = self._choice('uom', data.get('uom_id'), company, True)
            purchase_uom = self._choice('uom', data.get('uom_po_id') or uom.id, company, True)
            if uom.category_id != purchase_uom.category_id:
                raise ValidationError(_('Purchase unit must have the same category as the product unit.'))
            vals = dict(name=name, type=kind, purchase_ok=True, sale_ok=False,
                        company_id=company.id, categ_id=category.id, uom_id=uom.id,
                        uom_po_id=purchase_uom.id, default_code=str(data.get('default_code') or '')[:100])
            model = self._env(company)['product.product'].sudo().with_company(company)
            if 'is_storable' in model._fields:
                vals['is_storable'] = kind == 'consu' and bool(data.get('is_storable'))
            if data.get('property_account_expense_id'):
                vals['property_account_expense_id'] = self._choice('account', data['property_account_expense_id'], company, True).id
            if data.get('purchase_method') in ('purchase', 'receive'):
                vals['purchase_method'] = data['purchase_method']
            taxes = data.get('supplier_taxes_id')
            if taxes is not None:
                if not isinstance(taxes, list) or len(taxes) > 50:
                    raise ValidationError(_('Invalid purchase taxes.'))
                vals['supplier_taxes_id'] = [(6, 0, [self._choice('tax', t, company, True).id for t in taxes])]
            vals['barcode'] = str(data.get('barcode') or '')[:100] or False
            vals['description_purchase'] = str(data.get('description_purchase') or '')[:4000]
            if data.get('standard_price') not in (None, ''):
                cost = number(data['standard_price'], _('Cost'))
                if cost < 0:
                    raise ValidationError(_('Cost cannot be negative.'))
                vals['standard_price'] = cost
            product = model.create(vals)
            return {'id': product.id, 'label': product.display_name}
        return self._json(run)
