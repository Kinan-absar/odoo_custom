from urllib.parse import urlencode
from werkzeug.exceptions import Forbidden, NotFound
from odoo import http
from odoo.http import request
from odoo.osv import expression

BASE = '/my/employee/purchase-monitor'


class PortalPurchaseMonitor(http.Controller):
    def _user(self):
        user = request.env.user
        if (not user.has_group('absar_portal_purchase_monitor.group_portal_purchase_monitor')
                or not user.employee_id
                or user.has_group('employee_portal_suite.group_attendance_only')):
            raise Forbidden()
        return user

    def _domain(self, user):
        # Only confirmed (or completed) purchase orders in accessible companies.
        return [('state', 'in', ['purchase', 'done']), ('company_id', 'in', user.company_ids.ids)]

    def _signature(self, po):
        # Field names differ between installed Send-to-Sign PO releases.
        for fname in ('signature_state', 'sign_state', 'po_sign_state'):
            if fname in po._fields:
                value = po[fname]
                if value:
                    field = po._fields[fname]
                    selections = field._description_selection(po.env) if field.type == 'selection' else []
                    return dict(selections).get(value, str(value).replace('_', ' ').title())
        return 'Not available'

    def _project(self, po):
        for name in ('project_id', 'construction_project_id'):
            if name in po._fields and po[name]:
                return po[name].display_name
        if 'material_request_id' in po._fields and po.material_request_id:
            mr = po.material_request_id
            for name in ('project_id', 'construction_project_id'):
                if name in mr._fields and mr[name]:
                    return mr[name].display_name
        return '—'

    def _mr(self, po):
        if 'material_request_id' in po._fields and po.material_request_id:
            return po.material_request_id.display_name
        return '—'

    def _bill_data(self, pos):
        # Vendor bills are linked through purchase.order.line -> account.move.line.
        # Posted vendor invoices/refunds only. Financial figures are tax-inclusive.
        result = {po.id: {'invoiced': 0.0, 'paid': 0.0, 'due': 0.0} for po in pos}
        if not pos:
            return result
        # A bill can refer to multiple POs: allocate at bill-line level instead of
        # falsely assigning the entire bill to every linked PO.
        po_line_ids = {po.id: set(po.order_line.ids) for po in pos}
        all_lines = [i for lines in po_line_ids.values() for i in lines]
        aml = request.env['account.move.line'].sudo().search([
            ('purchase_line_id', 'in', all_lines),
            ('move_id.state', '=', 'posted'),
            ('move_id.move_type', 'in', ['in_invoice', 'in_refund']),
            ('display_type', '=', 'product'),
        ])
        by_move = {}
        for line in aml:
            by_move.setdefault(line.move_id.id, []).append(line)
        # Derive tax-inclusive values from posted bill line amounts and their taxes.
        # Bill payment settlement is allocated proportionally by bill lines; displayed
        # as an estimate where bills cover more than one PO.
        for lines in by_move.values():
            move = lines[0].move_id
            sign = -1 if move.move_type == 'in_refund' else 1
            total_lines = sum(abs(l.price_total) for l in move.invoice_line_ids if l.display_type == 'product')
            paid_ratio = 0.0 if not move.amount_total else max(0.0, min(1.0, (move.amount_total - move.amount_residual) / move.amount_total))
            for line in lines:
                value = sign * abs(line.price_total)
                for po in pos:
                    if line.purchase_line_id.id in po_line_ids[po.id]:
                        row = result[po.id]
                        row['invoiced'] += value
                        row['paid'] += value * paid_ratio
                        row['due'] += value * (1 - paid_ratio)
        for data in result.values():
            for key in data:
                data[key] = round(data[key], 2)
        return result

    def _rows(self, pos):
        finances = self._bill_data(pos)
        rows = []
        for po in pos:
            rows.append({
                'po': po, 'project': self._project(po), 'mr': self._mr(po),
                'signature': self._signature(po), 'financial': finances[po.id],
                'unbilled': max(0.0, po.amount_total - finances[po.id]['invoiced']),
            })
        return rows

    @http.route(BASE, type='http', auth='user', website=True)
    def list_orders(self, **kw):
        user = self._user()
        domain = self._domain(user)
        q = (kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', '|',
                ('name', 'ilike', q), ('partner_id.name', 'ilike', q),
                ('origin', 'ilike', q)]])
        po_model = request.env['purchase.order'].sudo()
        # Extra filters depend on what this Odoo instance exposes.
        source = kw.get('status', 'all')
        if source == 'purchase':
            domain.append(('state', '=', 'purchase'))
        elif source == 'done':
            domain.append(('state', '=', 'done'))
        total = po_model.search_count(domain)
        pages = max(1, (total + 19) // 20)
        try:
            page = min(max(int(kw.get('page', '1')), 1), pages)
        except (ValueError, TypeError):
            page = 1
        pos = po_model.search(domain, order='date_order desc,id desc', limit=20, offset=(page-1)*20)
        def page_url(n):
            args = {k: kw[k] for k in ('q','status') if kw.get(k)}
            args['page'] = n
            return BASE + '?' + urlencode(args)
        return request.render('absar_portal_purchase_monitor.purchase_monitor_list', {
            'rows': self._rows(pos), 'q': q, 'status': source,
            'total': total, 'page': page, 'pages': pages,
            'previous_url': page_url(page-1), 'next_url': page_url(page+1),
        })

    @http.route(BASE + '/<int:po_id>', type='http', auth='user', website=True)
    def order_detail(self, po_id, **kw):
        user = self._user()
        po = request.env['purchase.order'].sudo().browse(po_id).exists()
        if not po or po.state not in ('purchase', 'done') or po.company_id not in user.company_ids:
            raise NotFound()
        return request.render('absar_portal_purchase_monitor.purchase_monitor_detail', {
            'row': self._rows(po)[0],
        })
