import math
from urllib.parse import urlencode
from werkzeug.exceptions import NotFound
from odoo import http, fields
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.osv import expression
from .portal_prepare import PortalPurchasePrepare, integer

BASE = '/my/employee/purchase-monitor'
PREFIX = 'absar_portal_purchase_monitor.'


class PortalPurchaseMonitor(http.Controller):
    def _user(self):
        return PortalPurchasePrepare()._actor('monitor')

    def _rows(self, pos):
        result = []
        for po in pos:
            bills = po.order_line.invoice_lines.filtered(lambda l:
                l.move_id.state == 'posted' and l.move_id.move_type in ('in_invoice', 'in_refund') and
                l.display_type == 'product')
            billed = due = settled = 0.0
            allocated = False
            for move in bills.move_id:
                linked = bills.filtered(lambda l: l.move_id == move)
                value = sum(linked.mapped('price_total'))
                sign = -1 if move.move_type == 'in_refund' else 1
                all_lines = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
                denominator = sum(all_lines.mapped('price_total'))
                ratio = value / denominator if denominator else 0.0
                # Mixed PO/unlinked bill lines and partial settlements are explicit allocations.
                allocated = allocated or set(all_lines.ids) != set(linked.ids) or (
                    move.amount_residual and move.amount_residual != move.amount_total)
                date = move.invoice_date or move.date or fields.Date.context_today(po)
                convert = lambda amount: move.currency_id._convert(amount, po.currency_id, po.company_id, date)
                billed += convert(sign * value)
                due += convert(sign * move.amount_residual * ratio)
                settled += convert(sign * (move.amount_total - move.amount_residual) * ratio)
            signature = po.signature_status_text if 'signature_status_text' in po._fields else ''
            if not signature and 'signature_state' in po._fields:
                signature = dict(po._fields['signature_state']._description_selection(po.env)).get(po.signature_state, po.signature_state)
            project = po.project_id if 'project_id' in po._fields else po.absar_portal_project_id
            paid = None
            if 'amount_paid' in po._fields:
                field = po._fields['amount_paid']
                currency_field = getattr(field, 'currency_field', None)
                paid_currency = po[currency_field] if currency_field else po.company_id.currency_id
                if paid_currency == po.currency_id:
                    paid = po.amount_paid
            result.append(dict(po=po, project=project.display_name or '—',
                mr=po.material_request_id.display_name or '—', signature=signature or 'Not available',
                billed=po.currency_id.round(billed), due=po.currency_id.round(due),
                settled=po.currency_id.round(settled), allocated=allocated,
                paid=paid,
                unbilled=po.currency_id.round(max(0, po.amount_total - billed))))
        return result

    @http.route(BASE, type='http', auth='user', website=True)
    def list_orders(self, **kw):
        user = self._user()
        domain = [('state', 'in', ['purchase', 'done']), ('company_id', 'in', user.company_ids.ids)]
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            search = ['|', '|', '|', ('name', 'ilike', q), ('partner_id.name', 'ilike', q),
                      ('origin', 'ilike', q), ('material_request_id.name', 'ilike', q)]
            domain = expression.AND([domain, search])
        status = kw.get('status', 'all')
        if status in ('purchase', 'done'):
            domain.append(('state', '=', status))
        billing = kw.get('billing', 'all')
        if billing in ('to invoice', 'invoiced', 'no'):
            domain.append(('invoice_status', '=', billing))
        sort = kw.get('sort', 'date')
        sorts = {'date': 'date_order desc,id desc', 'reference': 'name,id desc',
                 'vendor': 'partner_id,id desc', 'amount': 'amount_total desc,id desc'}
        group_by = kw.get('group_by', '')
        group_fields = {'vendor': 'partner_id', 'buyer': 'user_id', 'company': 'company_id'}
        if 'project_id' in request.env['purchase.order']._fields:
            group_fields['project'] = 'project_id'
        group_field = group_fields.get(group_by)
        if not group_field:
            group_by = ''
        model = request.env['purchase.order'].sudo()
        total = model.search_count(domain)
        pages = max(1, math.ceil(total / 20))
        try:
            requested_page = integer(kw.get('page'), 1)
        except ValidationError:
            requested_page = 1
        page = min(max(requested_page, 1), pages)
        order = sorts.get(sort, sorts['date'])
        if group_field:
            order = group_field + ',' + order
        pos = model.search(domain, order=order, limit=20, offset=(page - 1) * 20)
        page_url = lambda n: BASE + '?' + urlencode(dict(q=q, status=status, billing=billing, sort=sort, group_by=group_by, page=n))
        return request.render(PREFIX + 'purchase_monitor_list', dict(
            rows=self._rows(pos), group_by=group_by, group_labels={po.id: po[group_field].display_name or 'Not set' for po in pos} if group_field else {}, q=q, status=status, billing=billing, sort=sort,
            total=total, page=page, pages=pages,
            previous_url=page_url(page - 1), next_url=page_url(page + 1)))

    @http.route(BASE + '/<int:po_id>', type='http', auth='user', website=True)
    def order_detail(self, po_id, **kw):
        user = self._user()
        po = request.env['purchase.order'].sudo().browse(po_id).exists()
        if not po or po.state not in ('purchase', 'done') or po.company_id not in user.company_ids:
            raise NotFound()
        return request.render(PREFIX + 'purchase_monitor_detail', dict(row=self._rows(po)[0]))
