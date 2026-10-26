import base64
from urllib.parse import urlencode
from odoo import http
from odoo.http import request,content_disposition
from odoo.exceptions import UserError
from werkzeug.exceptions import Forbidden,NotFound
BASE='/my/employee/purchase/vendor-invoices'
GROUP='customer_vendor_portal.group_vendor_invoice_reviewer'
class VendorInvoiceReview(http.Controller):
    def _scope(self,company_id):
        user=request.env.user
        if not user.active or not user.has_group(GROUP) or user.has_group('employee_portal_suite.group_attendance_only') or (user.share and not user.sudo().with_company(user.company_id).employee_id):raise Forbidden()
        try:cid=int(company_id or user.company_id.id)
        except (ValueError,TypeError):raise NotFound()
        company=user.sudo().company_ids.filtered(lambda item:item.id==cid)
        if not company:raise NotFound()
        env=request.env['portal.vendor.invoice'].with_context(allowed_company_ids=[cid]).with_company(company).sudo()
        domain=['&','|',('po_id','=',False),('po_id.company_id','=',cid),'|',('company_id','=',cid),'&',('company_id','=',False),('po_id.company_id','=',cid)]
        return env,company,domain

    def _record(self,ident,company_id):
        model,company,domain=self._scope(company_id)
        record=model.search(domain+[('id','=',ident)],limit=1)
        if not record or (record.po_id and record.po_id.company_id!=company):raise NotFound()
        return record,company

    @http.route(BASE,type='http',auth='user',website=True,methods=['GET'])
    def listing(self,company_id=None,q='',state='',page=1,**kw):
        model,company,domain=self._scope(company_id)
        if state in ('submitted','review','approved','rejected'):domain+=[('state','=',state)]
        if q:domain+=['|',('name','ilike',str(q)[:120]),('vendor_invoice_number','ilike',str(q)[:120])]
        page=max(1,min(int(page),100000));records=model.search(domain,order='id desc',offset=(page-1)*40,limit=40)
        return request.render('absar_portal_purchase_monitor.vendor_invoice_listing',dict(company=company,companies=request.env.user.sudo().company_ids,records=records,q=q,state=state,page=page,count=model.search_count(domain),urlencode=urlencode))

    @http.route(BASE+'/<int:ident>',type='http',auth='user',website=True,methods=['GET'])
    def detail(self,ident,company_id=None,message='',**kw):
        record,company=self._record(ident,company_id)
        return request.render('absar_portal_purchase_monitor.vendor_invoice_detail',dict(record=record,company=company,message=str(message)[:1000]))

    @http.route(BASE+'/<int:ident>/review',type='http',auth='user',methods=['POST'],csrf=True)
    def review(self,ident,company_id=None,version=None,operation=None,comment='',**kw):
        record,company=self._record(ident,company_id)
        try:
            with request.env.cr.savepoint():
                request.env.cr.execute('SELECT id FROM portal_vendor_invoice WHERE id=%s FOR UPDATE',[record.id]);record.invalidate_recordset()
                self._record(ident,company.id)
                if not version or version!=str(record.write_date):raise UserError('This invoice changed. Reopen it before reviewing.')
                if operation not in ('review','approved','rejected'):raise Forbidden()
                if record.state not in ('submitted','review'):raise UserError('This submission is already decided.')
                if (operation=='review' and record.state!='submitted') or (operation in ('approved','rejected') and record.state!='review'):raise UserError('Move the submission to Under Review before deciding.')
                if operation=='rejected' and not comment.strip():raise UserError('Enter a comment for the vendor before rejecting.')
                record.write({'review_comment':str(comment).strip()[:4000]})
                getattr(record,{'review':'action_set_review','approved':'action_approve','rejected':'action_reject'}[operation])()
            return request.redirect(BASE+'/'+str(ident)+'?company_id='+str(company.id))
        except UserError as exc:return request.redirect(BASE+'/'+str(ident)+'?'+urlencode(dict(company_id=company.id,message=str(exc))))

    @http.route(BASE+'/<int:ident>/document',type='http',auth='user',methods=['GET'])
    def document(self,ident,company_id=None,**kw):
        record,company=self._record(ident,company_id);attachment=record.attachment_id
        if not attachment or attachment.type!='binary' or attachment.res_model!='portal.vendor.invoice' or attachment.res_id!=record.id:raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b''),headers=[('Content-Type','application/octet-stream'),('Content-Disposition',content_disposition(attachment.name or 'vendor-invoice')),('Cache-Control','private, no-store'),('X-Content-Type-Options','nosniff')])
