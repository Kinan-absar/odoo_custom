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
from .portal_purchase import PortalPurchaseMonitor


class PortalPurchaseDirectory(PortalPurchasePrepare):
    """Dedicated portal pages; every elevated query is explicitly scoped."""

    def _page(self, model, domain, kw, base, order='id desc', **params):
        count = model.search_count(domain)
        page = max(1, min(integer(kw.get('page'), 1), max(1, math.ceil(count / 20))))
        page_url = lambda n: base + '?' + urlencode(dict(params, page=n))
        return dict(records=model.search(domain, order=order, limit=20, offset=(page-1)*20),
                    page=page, pages=max(1, math.ceil(count/20)), total=count,
                    previous_url=page_url(page-1), next_url=page_url(page+1))

    @http.route(BASE + '/<int:po_id>/create-bill', type='http', auth='user', methods=['POST'], csrf=True)
    def create_vendor_bill(self,po_id,**kw):
        def run(data):
            self._actor('user')
            po=self._record(po_id)
            if 'pbw.portal.accounting.service' not in request.env:
                raise ValidationError(_('Install the employee accounting workspace to prepare the vendor bill.'))
            service=request.env['pbw.portal.accounting.service']
            company=service._company(po.company_id.id)
            return service._create_bill_from_po(company,po.id,data.get('version'))
        return self._json(run)

    @http.route(BASE + '/<int:po_id>/receipts', type='http', auth='user', methods=['POST'], csrf=True)
    def receipts(self, po_id, **kw):
        def run(data):
            po = self._record(po_id)
            return {'receipts': po._pbw_purchase_receipts()}
        return self._json(run)

    @http.route(BASE + '/<int:po_id>/receive', type='http', auth='user', methods=['POST'], csrf=True)
    def receive(self, po_id, **kw):
        def run(data):
            po = self._record(po_id)
            result = po._pbw_purchase_receive(data.get('receipt_id'), data.get('version'), data.get('quantities'))
            result['url'] = BASE + '/%s' % po.id
            return result
        return self._json(run)

    @http.route(BASE + '/orders', type='http', auth='user', website=True)
    def orders(self, **kw):
        user = self._actor()
        if user.has_group(PREFIX + 'group_portal_purchase_monitor'):
            return request.redirect('/my/workspace/purchase-monitor')
        if not user.has_group(PREFIX + 'group_portal_purchase_preparer'):
            return request.redirect(BASE + '/approvals')
        values = PortalPurchaseMonitor()._list_values(
            user, kw, extra_domain=[] if user.has_group(PREFIX+'group_portal_purchase_user') else [('pbw_portal_preparer_id', '=', user.id)],
            list_url=BASE + '/orders', detail_base_url=BASE,
            title='Purchase Orders', description='All purchase orders in your allowed companies' if user.has_group(PREFIX+'group_portal_purchase_user') else 'Your confirmed purchase orders', show_workspace=True)
        return request.render(PREFIX + 'purchase_monitor_list', values)

    @http.route(BASE + '/products', type='http', auth='user', website=True)
    def products(self, **kw):
        user = self._actor('preparer')
        company = self._company(kw.get('company_id'))
        model, domain, order = self._scope('product', company)
        q = str(kw.get('q') or '').strip()[:120]
        if q:
            domain = expression.AND([domain, ['|', ('name','ilike',q), ('default_code','ilike',q)]])
        values = self._page(model, domain, kw, BASE+'/products', order='name,id', q=q, company_id=company.id)
        values.update(q=q, company=company, companies=user.company_ids,
                      can_create=user.has_group(PREFIX+'group_portal_purchase_preparer'))
        return request.render(PREFIX+'purchase_product_directory', values)




    @http.route([BASE + '/new', BASE + '/<int:po_id>'], type='http', auth='user', website=True)
    def editor(self, po_id=None, **kw):
        po = self._record(po_id) if po_id else False
        boot = self._boot(po)
        if po and kw.get('from_monitor') == '1' and request.env.user.has_group(PREFIX + 'group_portal_purchase_monitor'):
            boot.update(back_url='/my/workspace/purchase-monitor', approval_view=False)
        monitoring = PortalPurchaseMonitor()._rows(po)[0] if po and po.state in ('purchase', 'done') else False
        return request.render(PREFIX + 'purchase_prepare_detail', dict(boot_json=json.dumps(boot), boot=boot, po=po, monitoring=monitoring))

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
            po._pbw_purchase_lock()
            if not po._pbw_purchase_editable(request.env.user):
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
