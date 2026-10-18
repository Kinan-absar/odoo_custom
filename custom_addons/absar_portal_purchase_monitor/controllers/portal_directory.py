import json
import base64
import binascii
import math
from urllib.parse import urlencode
from werkzeug.exceptions import NotFound
from odoo import http, _, fields
from odoo.exceptions import ValidationError
from odoo.http import content_disposition
from odoo.http import request
from odoo.osv import expression
from .portal_prepare import PortalPurchasePrepare, BASE, PREFIX, integer


class PortalPurchaseDirectory(PortalPurchasePrepare):
    """Dedicated portal pages; every elevated query is explicitly scoped."""

    def _page(self, model, domain, kw, base, order='id desc', **params):
        count = model.search_count(domain)
        page = max(1, min(integer(kw.get('page'), 1), max(1, math.ceil(count / 20))))
        page_url = lambda n: base + '?' + urlencode(dict(params, page=n))
        return dict(records=model.search(domain, order=order, limit=20, offset=(page-1)*20),
                    page=page, pages=max(1, math.ceil(count/20)), total=count,
                    previous_url=page_url(page-1), next_url=page_url(page+1))

    @http.route(BASE + '/orders', type='http', auth='user', website=True)
    def orders(self, **kw):
        user = self._actor()
        if user.has_group(PREFIX + 'group_portal_purchase_monitor'):
            return request.redirect('/my/employee/purchase-monitor')
        scope = []
        if user.has_group(PREFIX + 'group_portal_purchase_monitor'):
            scope.append([(1, '=', 1)])
        if user.has_group(PREFIX + 'group_portal_purchase_preparer'):
            scope.append([('absar_portal_preparer_id', '=', user.id)])
        if any(user.has_group(PREFIX + 'group_portal_purchase_' + r) for r in ('approver',)):
            scope.append([('absar_portal_preparer_id', '!=', False)])
        domain = expression.AND([[('company_id', 'in', user.company_ids.ids), ('state', 'in', ['purchase', 'done'])], expression.OR(scope)])
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', '|', ('name', 'ilike', q), ('partner_id.name', 'ilike', q), ('material_request_id.name', 'ilike', q)]])
        sort = kw.get('sort', 'newest')
        sorts = {'newest':'id desc', 'reference':'name asc,id desc', 'vendor':'partner_id,id desc', 'amount':'amount_total desc,id desc', 'date':'date_order desc,id desc'}
        group_by = kw.get('group_by', '')
        groups = {'vendor':'partner_id', 'project':'project_id', 'buyer':'user_id', 'company':'company_id', 'review':'absar_portal_review_state'}
        field = groups.get(group_by)
        values = self._page(request.env['purchase.order'].sudo(), domain, kw, BASE+'/orders',
                            order=(field+',' if field else '')+sorts.get(sort,sorts['newest']), q=q, sort=sort, group_by=group_by)
        pos = values.pop('records')
        values.update(orders=pos, orders_only=True, approval=False, confirmations=False,
                      q=q, review='all', sort=sort, group_by=group_by if field else '',
                      group_labels={po.id: (dict(po._fields[field]._description_selection(po.env)).get(po[field], 'Not set') if field=='absar_portal_review_state' else po[field].display_name or 'Not set') for po in pos} if field else {})
        return request.render(PREFIX+'purchase_prepare_list', values)

    @http.route(BASE + '/products', type='http', auth='user', website=True)
    def products(self, **kw):
        user = self._actor()
        company = self._company(kw.get('company_id'))
        model, domain, order = self._scope('product', company)
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', ('name','ilike',q), ('default_code','ilike',q)]])
        values = self._page(model, domain, kw, BASE+'/products', order='name,id', q=q, company_id=company.id)
        values.update(q=q, company=company, companies=user.company_ids,
                      can_create=user.has_group(PREFIX+'group_portal_purchase_preparer'))
        return request.render(PREFIX+'purchase_product_directory', values)

    @http.route(BASE + '/material-requests', type='http', auth='user', website=True)
    def materials(self, **kw):
        user = self._actor('preparer')
        company = self._company(kw.get('company_id'))
        model, domain, order = self._scope('mr', company)
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', ('name','ilike',q), ('project_id.name','ilike',q)]])
        values = self._page(model, domain, kw, BASE+'/material-requests', q=q, company_id=company.id)
        values.update(q=q, company=company, companies=user.company_ids)
        return request.render(PREFIX+'purchase_mr_directory', values)

    def _mr_data(self, mr, company):
        """Propose lines without creating products or orders as a side effect."""
        product_model, product_domain, order = self._scope('product', company)
        lines = []
        if len(mr.line_ids) > 300:
            raise ValidationError(_('This Material Request has more than 300 materials. Split it into smaller RFQs.'))
        for row in mr.line_ids:
            products = product_model.search(expression.AND([product_domain, [('name', '=', row.item_name or '')]]), limit=2)
            product = products if len(products)==1 else product_model.browse()
            if product and row.uom_id and product.uom_id.category_id != row.uom_id.category_id:
                product = product_model.browse()
            uom = row.uom_id or product.uom_po_id
            lines.append(dict(id=0, display_type='', name=row.item_name or '', product_id=product.id or 0,
                product_label=product.display_name or '', product_qty=row.qty_required,
                product_uom=uom.id or 0, uom_label=uom.display_name or '', price_unit=0,
                discount=0, taxes_id=[], taxes=[], analytic_distribution={}, analytic_labels={},
                date_planned=(str(mr.delivery_date)+'T08:00:00') if mr.delivery_date else '',
                absar_expense_account_id=0, account_label='', default_account='', qty_received=0, qty_invoiced=0))
        return dict(id=mr.id, name=mr.name, project={'id':mr.project_id.id,'label':mr.project_id.display_name}, lines=lines)

    @http.route(BASE + '/mr-info', type='http', auth='user', methods=['POST'], csrf=True)
    def mr_info(self, **kw):
        def run(data):
            self._actor('preparer')
            company = self._company(data.get('company_id'))
            mr = self._choice('mr', data.get('mr_id'), company, True)
            return self._mr_data(mr, company)
        return self._json(run)

    @http.route([BASE + '/new', BASE + '/<int:po_id>'], type='http', auth='user', website=True, methods=['GET'])
    def editor(self, po_id=None, mr_id=None, **kw):
        po = self._record(po_id) if po_id else False
        if po and request.env.user.has_group(PREFIX + 'group_portal_purchase_monitor') and po.state in ('purchase', 'done'):
            return request.redirect('/my/employee/purchase-monitor/%s' % po.id)
        company = None
        mr = False
        if not po and mr_id:
            self._actor('preparer')
            candidate = request.env['material.request'].sudo().browse(integer(mr_id)).exists()
            if not candidate:
                raise NotFound()
            company = self._company((candidate.project_id.company_id or candidate.employee_id.company_id).id)
            mr = self._choice('mr', candidate.id, company, True)
        boot = self._boot(po, company=company)
        if mr:
            info = self._mr_data(mr, company)
            boot['values'].update(material_request_id=mr.id, project_id=mr.project_id.id,
                                  origin=mr.name, lines=info['lines'])
            boot['selected'].update(material_request_id={'id':mr.id,'label':mr.name}, project_id=info['project'])
            boot['mr_source'] = mr.name
        return request.render(PREFIX+'purchase_prepare_detail', dict(boot_json=json.dumps(boot), boot=boot, po=po))

    @http.route([BASE+'/app', BASE+'/app/<path:action_path>'], type='http', auth='user', website=True)
    def legacy_native_url(self, action_path=None, **kw):
        # Inert compatibility for bookmarked native-host URLs. Never reload backend assets.
        user = self._actor()
        target = BASE if user.has_group(PREFIX+'group_portal_purchase_preparer') else BASE+'/approvals' if user.has_group(PREFIX+'group_portal_purchase_approver') else BASE+'/orders'
        return request.redirect(target)

    @http.route(BASE + '/<int:po_id>/quotation-upload', type='http', auth='user', methods=['POST'], csrf=True)
    def quotation_upload(self, po_id, **kw):
        def run(data):
            po = self._record(po_id, edit=True)
            po._portal_lock()
            if not po._portal_editable(request.env.user):
                raise ValidationError(_('This RFQ is no longer editable.'))
            if str(po.write_date) != data.get('version'):
                raise ValidationError(_('This RFQ changed. Reload before adding the quotation.'))
            try:
                raw = base64.b64decode(data.get('data') or '', validate=True)
            except (ValueError, binascii.Error):
                raise ValidationError(_('Invalid PDF upload.'))
            # The common portal request cap is 2 MB including base64 encoding.
            if not raw.startswith(b'%PDF-') or len(raw) > 1_400_000:
                raise ValidationError(_('Choose a PDF no larger than 1.4 MB.'))
            name = str(data.get('name') or 'Supplier quotation.pdf').replace('/', '_').replace('\\', '_').replace('\r', '').replace('\n', '')[:180]
            if not name.lower().endswith('.pdf'):
                name += '.pdf'
            attachment = request.env['ir.attachment'].sudo().with_company(po.company_id).create({
                'name': name, 'type': 'binary', 'datas': base64.b64encode(raw), 'mimetype': 'application/pdf',
                'res_model': 'purchase.order', 'res_id': po.id, 'company_id': po.company_id.id,
            })
            if 'quotation_attachment_ids' in po._fields:
                po.write({'quotation_attachment_ids': [(4, attachment.id)]})
            # Invalidate the optimistic version even when only a generic attachment is added.
            po.write({'write_date': fields.Datetime.now()})
            return {'id':attachment.id, 'name':attachment.name, 'version':str(po.write_date)}
        return self._json(run)

    @http.route(BASE + '/<int:po_id>/attachments/<int:attachment_id>', type='http', auth='user', methods=['GET'])
    def attachment_download(self, po_id, attachment_id, **kw):
        po = self._record(po_id)
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if (not attachment or attachment.res_model != 'purchase.order' or attachment.res_id != po.id or
                (attachment.company_id and attachment.company_id != po.company_id)):
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b''), headers=[
            ('Content-Type', 'application/pdf' if attachment.mimetype == 'application/pdf' else 'application/octet-stream'),
            ('Content-Disposition', content_disposition(attachment.name)), ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'private, no-store')])

    @http.route(BASE + '/<int:po_id>/print', type='http', auth='user', methods=['GET'])
    def print_document(self, po_id, **kw):
        po = self._record(po_id)
        report = 'purchase.report_purchase_quotation' if po.state in ('draft', 'sent') else 'purchase.action_report_purchase_order'
        pdf, _kind = request.env['ir.actions.report'].sudo().with_company(po.company_id)._render_qweb_pdf(report, res_ids=[po.id])
        return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'),
            ('Content-Disposition', content_disposition(po.name + '.pdf')), ('Cache-Control', 'private, no-store'),
            ('X-Content-Type-Options', 'nosniff')])
