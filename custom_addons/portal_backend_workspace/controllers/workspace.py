"""Functional foundation for four Odoo business workspaces.

This is *not* a transplant of the four legacy feature sets. All record access here
uses an explicit workspace group + company restriction, and writes are draft-only.
"""
from datetime import date
from werkzeug.exceptions import BadRequest, Forbidden, NotFound
from odoo import http
from odoo.http import request
# Only core Odoo modules are required. No EPS or other custom addon imports.

def workspace_user(user):
    return bool(user and user.share and not user._is_public() and user.has_group(
        'portal_backend_workspace.group_workspace_user'))

SECTIONS = {
 'sales': {'title':'Sales','description':'Quotations and sales orders','icon':'fa-line-chart', 'model':'sale.order', 'group':'portal_backend_workspace.group_workspace_sales', 'name_field':'name', 'fields':[('name','Number'),('partner_id','Customer'),('date_order','Date'),('state','Status'),('amount_total','Total')]},
 'purchase': {'title':'Purchase','description':'Purchase orders','icon':'fa-shopping-cart', 'model':'purchase.order', 'group':'portal_backend_workspace.group_workspace_purchase', 'name_field':'name','fields':[('name','Number'),('partner_id','Vendor'),('date_order','Date'),('state','Status'),('amount_total','Total')]},
 'accounting': {'title':'Accounting','description':'Vendor bills and customer invoices','icon':'fa-calculator', 'model':'account.move', 'group':'portal_backend_workspace.group_workspace_accounting','name_field':'name','fields':[('name','Number'),('partner_id','Partner'),('invoice_date','Bill / Invoice Date'),('state','Status'),('amount_total','Total')]},
 'hr': {'title':'HR Administration','description':'Employees, company and contact details','icon':'fa-users', 'model':'hr.employee', 'group':'portal_backend_workspace.group_workspace_hr','name_field':'name','fields':[('name','Employee'),('department_id','Department'),('job_title','Job Title'),('work_email','Email')]},
}

def _sections():
 user=request.env.user
 if not workspace_user(user): raise Forbidden()
 return [dict(key=k,**{x:v for x,v in s.items() if x in ('title','description','icon')}) for k,s in SECTIONS.items() if user.has_group(s['group'])]

def _section(name):
 if name not in SECTIONS: raise NotFound()
 sec=SECTIONS[name]
 if not workspace_user(request.env.user) or not request.env.user.has_group(sec['group']): raise Forbidden()
 return sec

def _domain(section):
 domain=[('company_id','=',request.env.user.company_id.id)]
 if section == 'accounting': domain += [('move_type','in',('in_invoice','out_invoice'))]
 return domain

def _label(value):
 if not value: return '—'
 if hasattr(value,'display_name'): return value.display_name
 if isinstance(value,(date,)): return str(value)
 return str(value)

def _context(section, active=None):
 return {'sections':_sections(), 'active_section':active or section, 'company_name': request.env.user.company_id.name}

class PortalBackendWorkspace(http.Controller):
 @http.route('/my/workspace',type='http',auth='user',website=True,methods=['GET'])
 def dashboard(self,**kw):
  return request.render('portal_backend_workspace.workspace_dashboard',_context('home'))

 @http.route('/my/workspace/<string:section>',type='http',auth='user',website=True,methods=['GET'])
 def section(self,section,**kw):
  sec=_section(section)
  Model=request.env[sec['model']].sudo()
  records=Model.search(_domain(section),order='id desc',limit=50)
  items=[{'id':rec.id,'cells':[_label(rec[field]) for field,_ in sec['fields']]} for rec in records]
  values=_context(section)
  values.update({'section':dict(key=section,**sec),'columns':[name for _,name in sec['fields']],'items':items})
  return request.render('portal_backend_workspace.workspace_records',values)

 @http.route('/my/workspace/<string:section>/record/<int:record_id>',type='http',auth='user',website=True,methods=['GET'])
 def record(self,section,record_id,**kw):
  sec=_section(section)
  rec=request.env[sec['model']].sudo().search([('id','=',record_id)]+_domain(section),limit=1)
  if not rec: raise NotFound()
  values=_context(section)
  values.update({'section':dict(key=section,**sec),'record_title':_label(rec[sec['name_field']]),'properties':[{'label':label,'value':_label(rec[field])} for field,label in sec['fields']]})
  return request.render('portal_backend_workspace.workspace_record',values)

 @http.route('/my/workspace/<string:section>/new',type='http',auth='user',website=True,methods=['GET'])
 def new(self,section,**kw):
  sec=_section(section)
  partners=[]
  if section!='hr':
   # Only partners of the selected company or shared partners.
   partner_model=request.env['res.partner'].sudo()
   partners=partner_model.search(['|',('company_id','=',False),('company_id','=',request.env.user.company_id.id)],order='name',limit=200)
  values=_context(section)
  values.update({'section':dict(key=section,**sec),'partners':partners,'error':request.params.get('error')})
  return request.render('portal_backend_workspace.workspace_new',values)

 @http.route('/my/workspace/<string:section>/create',type='http',auth='user',website=True,methods=['POST'],csrf=True)
 def create(self,section,**kw):
  sec=_section(section)
  company=request.env.user.company_id
  if section=='hr':
   name=(kw.get('name') or '').strip()
   if not name or len(name)>200: raise BadRequest('An employee name is required.')
   data={'name':name,'company_id':company.id}
   email=(kw.get('work_email') or '').strip()
   if email: data['work_email']=email[:200]
  else:
   try: partner_id=int(kw.get('partner_id') or 0)
   except (ValueError,TypeError): raise BadRequest('Invalid partner')
   partner=request.env['res.partner'].sudo().search([('id','=',partner_id),'|',('company_id','=',False),('company_id','=',company.id)],limit=1)
   if not partner: raise BadRequest('Select a valid partner')
   data={'partner_id':partner.id,'company_id':company.id}
   if section=='sales': data['state']='draft'
   if section=='purchase': data['state']='draft'
   if section=='accounting':
    typ=kw.get('move_type')
    if typ not in ('in_invoice','out_invoice'): raise BadRequest('Invalid invoice type')
    data.update({'move_type':typ,'invoice_date':date.today(),'state':'draft'})
  # No arbitrary model, fields, state transitions, or user-provided company IDs.
  rec=request.env[sec['model']].sudo().with_company(company).create(data)
  return request.redirect('/my/workspace/%s/record/%d'%(section,rec.id))
