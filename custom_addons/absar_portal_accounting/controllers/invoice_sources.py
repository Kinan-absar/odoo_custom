from urllib.parse import urlencode
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError,UserError,ValidationError
from werkzeug.exceptions import Forbidden
BASE='/my/employee/accounting'
class InvoiceSources(http.Controller):
    def _service(self,company_id):
        if not request.env.user.share:raise Forbidden()
        service=request.env['absar.portal.accounting.service'];company=service._company(company_id);service._kind('invoices')
        return service,company

    @http.route(BASE+'/invoice-sources/<string:kind>',type='http',auth='user',website=True,methods=['GET'])
    def sources(self,kind,company_id=None,page=1,q='',message='',**kw):
        service,company=self._service(company_id);model,domain=service._source_domain(company,kind)
        if q:domain+=[('name','ilike',str(q)[:120])]
        page=max(1,min(int(page),100000));records=service._env(company)[model].search(domain,order='id desc',offset=(page-1)*40,limit=40)
        total=service._env(company)[model].search_count(domain)
        return request.render('absar_portal_accounting.invoice_sources',dict(company=company,companies=request.env.user.sudo().company_ids,configured=bool(company.portal_accounting_journal_ids),kinds=service._kinds(),kind=kind,records=records,page=page,total=total,q=q,message=str(message)[:1000],roles=service._actor(kind='invoices')[1],urlencode=urlencode))

    @http.route(BASE+'/invoice-sources/<string:kind>/<int:ident>/create',type='http',auth='user',methods=['POST'],csrf=True)
    def create_invoice(self,kind,ident,company_id=None,version=None,**kw):
        service,company=self._service(company_id)
        try:
            with request.env.cr.savepoint():move=service._source_invoice(company,kind,ident,version)
            return request.redirect(BASE+'/invoices/%s?company_id=%s'%(move.id,company.id))
        except (AccessError,UserError,ValidationError) as exc:
            return request.redirect(BASE+'/invoice-sources/'+kind+'?'+urlencode(dict(company_id=company.id,message=str(exc))))
