import io
from urllib.parse import urlencode
import xlsxwriter
from odoo import http, fields, _
from odoo.http import request, content_disposition
from odoo.exceptions import AccessError, UserError, ValidationError
from werkzeug.exceptions import Forbidden, NotFound
from ..models.gateway import KINDS, PREFIX

BASE='/my/employee/admin'
HEADERS={
 'employees':['Employee','Department','Job','Work Location','Manager','Work Email','Status'],
 'attendance':['Employee','Check In','Check Out','Hours','Project','Exception'],
 'contracts':['Contract','Employee','Start','End','Wage','Status'],
 'work-entries':['Description','Employee','Type','Start','End','Status'],
 'payslips':['Payslip','Employee','From','To','Gross','Net','Status'],
 'batches':['Batch','From','To','Payslips','Status'],
 'salary-reports':['Report','From','To','Employees','Estimated Net','Status'],
}

class EmployeeAdminPortal(http.Controller):
    def _service(self):
        service=request.env['absar.employee.admin.gateway']
        try:service._actor()
        except AccessError as exc:raise Forbidden(str(exc))
        return service

    def _url(self,kind='',ident=None,**params):
        path=BASE+('/'+kind if kind else '')+('/'+str(ident) if ident else '')
        return path+('?' + urlencode(params) if params else '')

    def _context(self,s,company,**kw):
        user,roles=s._actor()
        result=dict(base=BASE,company=company,companies=user.company_ids,roles=roles,
            nav=[(k,spec[1]) for k,spec in KINDS.items() if roles[spec[2]]],
            tz=user.tz or 'UTC',kind='',notice='')
        result.update(kw);return result

    def _date(self,v):return fields.Date.to_date(v).strftime('%d/%m/%Y') if v else '—'
    def _dt(self,s,v):return fields.Datetime.context_timestamp(s,fields.Datetime.to_datetime(v)).strftime('%d/%m/%Y %H:%M') if v else '—'
    def _state(self,s,r):return s._selection(r,'state').get(r.state,r.state) if 'state' in r._fields else ''
    def _money(self,c,v):return '{:,.2f} {}'.format(v or 0,c.currency_id.name)

    def _cells(self,s,c,kind,r):
        money=lambda v:self._money(c,v)
        if kind=='employees':return [r.name,r.department_id.name or '—',r.job_title or '—',r.work_location_id.name or '—',r.parent_id.name or '—',r.work_email or '—',_('Active') if r.active else _('Archived')]
        if kind=='attendance':return [r.employee_id.name,self._dt(s,r.check_in),self._dt(s,r.check_out),'{:.2f}'.format(r.worked_hours),r.check_in_project_id.display_name or '—',_('Pending Review') if (r.auto_checked_out or r.checkout_outside_location) and r.attendance_exception_state=='pending' else _('Resolved') if r.attendance_exception_state=='resolved' else '—']
        if kind=='contracts':return [r.name,r.employee_id.name,self._date(r.date_start),self._date(r.date_end),money(r.wage),self._state(s,r)]
        if kind=='work-entries':return [r.name,r.employee_id.name,r.work_entry_type_id.name,self._dt(s,r.date_start),self._dt(s,r.date_stop),self._state(s,r)]
        if kind=='payslips':
            net=r.net_wage if 'net_wage' in r._fields else sum(r.line_ids.filtered(lambda l:l.code=='NET').mapped('total'))
            gross=r.gross_wage if 'gross_wage' in r._fields else sum(r.line_ids.filtered(lambda l:l.code=='GROSS').mapped('total'))
            return [r.name or r.number or _('Draft'),r.employee_id.name,self._date(r.date_from),self._date(r.date_to),money(gross),money(net),self._state(s,r)]
        if kind=='batches':
            s._batch_scope(c,r)
            return [r.name,self._date(r.date_start),self._date(r.date_end),str(len(r.slip_ids)),self._state(s,r)]
        s._report_scope(c,r)
        return [r.name,self._date(r.date_from),self._date(r.date_to),str(r.total_employees),money(r.total_net_salary),self._state(s,r)]

    @http.route(BASE,type='http',auth='user',website=True,methods=['GET'])
    def home(self,company_id=None,**kw):
        s=self._service();c=s._company(company_id);roles=s._actor()[1]
        cards=[dict(title=spec[1],count=s._env(c)[spec[0]].search_count(s._domain(c,k)),url=self._url(k,company_id=c.id)) for k,spec in KINDS.items() if roles[spec[2]]]
        return request.render(PREFIX+'home',self._context(s,c,cards=cards))

    @http.route(BASE+'/contract-options',type='http',auth='user',methods=['GET'])
    def contract_options(self,company_id=None,kind='payslips',employee_id=None,**kw):
        s=self._service();c=s._company(company_id)
        try:options=s._contract_choices(c,kind,employee_id)
        except AccessError as exc:raise Forbidden(str(exc))
        return request.make_json_response({'options':options},headers=[('Cache-Control','private, no-store')])

    @http.route(BASE+'/<string:kind>',type='http',auth='user',website=True,methods=['GET'])
    def listing(self,kind,company_id=None,q='',state='',employee_id=None,page=1,date_from='',date_to='',**kw):
        s=self._service();c=s._company(company_id)
        try:
            result=s._list(c,kind,q,state,employee_id,page,date_from,date_to)
            rows=[dict(id=r.id,cells=self._cells(s,c,kind,r),url=self._url(kind,r.id,company_id=c.id)) for r in result.pop('records')]
        except AccessError as exc:raise Forbidden(str(exc))
        except (ValueError,ValidationError) as exc:raise NotFound(str(exc))
        params=dict(company_id=c.id,q=q,state=state,employee_id=employee_id or '',date_from=date_from,date_to=date_to)
        return request.render(PREFIX+'listing',self._context(s,c,kind=kind,title=KINDS[kind][1],rows=rows,headers=HEADERS[kind],q=q,state=state,date_from=date_from,date_to=date_to,
            previous_url=self._url(kind,page=result['page']-1,**params),next_url=self._url(kind,page=result['page']+1,**params),**result))

    def _detail_values(self,s,c,kind,ident=None,notice=''):
        s._kind(kind);r=s._record(c,kind,ident) if ident else False
        if kind=='salary-reports' and r:s._report_scope(c,r)
        if kind=='batches' and r:s._batch_scope(c,r)
        groups=s._groups(c,kind,r);tables=[];adjustments=[];totals=[];slips=[]
        money=lambda v:self._money(c,v)
        if r and kind=='payslips':
            tables.append(dict(title='Worked Days',headers=['Type','Days','Hours','Amount'],rows=[[l.name,l.number_of_days,l.number_of_hours,money(l.amount)] for l in r.worked_days_line_ids]))
            tables.append(dict(title='Salary Computation',headers=['Code','Rule','Quantity','Rate','Total'],rows=[[l.code,l.name,l.quantity,l.rate,money(l.total)] for l in r.line_ids]))
            for name in ('x_studio_total_deduction','x_studio_float_field_10f_1j131bp4a','x_studio_reimbursement','x_studio_unpaid','x_studio_deduct_other','x_studio_deduct_loan'):
                if name in r._fields:totals.append((r._fields[name].string,money(r[name])))
            adjustments=[dict(id=l.id,name=l.name,amount=l.amount,input_type_id=l.input_type_id.id) for l in r.input_line_ids]
        if r and kind=='salary-reports':
            tables.append(dict(title='Attendance Salary Summary',headers=['Employee','Work Location','Basic','Allowances','Worked Hours','Attendance Deduction','Other Deductions','Reimbursements','Estimated Net'],rows=[
                [l.employee_id.name,l.work_location_id.name or '—',money(l.basic_salary),money(l.total_allowances),l.worked_hours,money(l.attendance_deduction),money(l.other_deductions),money(l.reimbursements),money(l.net_salary)] for l in r.line_ids]))
            totals=[('Estimated Net',money(r.total_net_salary)),('Attendance Deductions',money(r.total_attendance_deductions)),('Other Deductions',money(r.total_other_deductions)),('Reimbursements',money(r.total_reimbursements))]
            adjustments=[dict(id=l.id,name=l.employee_id.name,manual_absent_days=l.manual_absent_days,other_deductions=l.other_deductions,reimbursements=l.reimbursements) for l in r.line_ids]
        if r and kind=='batches':
            slips=[dict(url=self._url('payslips',p.id,company_id=c.id),cells=self._cells(s,c,'payslips',p)) for p in r.slip_ids]
        audit=s._env(c)['absar.employee.admin.audit'].search([('company_id','=',c.id),('resource','=',kind),('resource_id','=',r.id)],limit=30,order='id desc') if r else []
        types=s._env(c)['hr.payslip.input.type'].search(s._relation_domain(c,'hr.payslip.input.type'),limit=1000) if kind=='payslips' else []
        attendance_info=[]
        if r and kind=='attendance':
            for name in ('in_mode','out_mode','auto_checked_out','checkout_outside_location','attendance_exception_state','x_studio_location'):
                if name in r._fields:
                    f=r._fields[name];v=r[name]
                    if f.type=='selection':v=s._selection(r,name).get(v,v)
                    elif f.type=='many2one':v=v.display_name or '—'
                    elif f.type=='boolean':v=_('Yes') if v else _('No')
                    attendance_info.append((f.string,v or '—'))
        return self._context(s,c,kind=kind,title=KINDS[kind][1],rec=r,groups=groups,admin_can_edit=s._editable(kind,r),version=str(r.write_date) if r else '',notice=notice,
            tables=tables,totals=totals,adjustments=adjustments,slips=slips,audit=audit,input_types=types,attendance_info=attendance_info,
            form_url=self._url(kind,r.id if r else 'new')+'/save',record_url=self._url(kind,r.id) if r else '',back_url=self._url(kind,company_id=c.id))

    @http.route([BASE+'/<string:kind>/new',BASE+'/<string:kind>/<int:ident>'],type='http',auth='user',website=True,methods=['GET'])
    def detail(self,kind,ident=None,company_id=None,**kw):
        s=self._service();c=s._company(company_id)
        try:
            values=self._detail_values(s,c,kind,ident,str(kw.get('notice') or '')[:1000])
            if not ident and kind=='payslips' and kw.get('batch_id'):
                batch=s._relation(c,'hr.payslip.run',kw['batch_id']);s._batch_scope(c,batch)
                if batch.state not in ('draft','verify'):raise UserError(_('This batch is finalized.'))
                defaults={'payslip_run_id':batch.id,'date_from':str(batch.date_start),'date_to':str(batch.date_end)}
                for group,items in values['groups']:
                    for item in items:
                        if item['name'] in defaults:item['value']=defaults[item['name']]

        except AccessError as exc:raise Forbidden(str(exc))
        return request.render(PREFIX+'detail',values)

    @http.route([BASE+'/<string:kind>/new/save',BASE+'/<string:kind>/<int:ident>/save'],type='http',auth='user',website=True,methods=['POST'],csrf=True)
    def save(self,kind,ident=None,**post):
        s=self._service();c=s._company(post.get('company_id'))
        try:
            with request.env.cr.savepoint():
                data=dict(post,id=ident);model=s._env(c)[s._kind(kind)[0]]
                for group,names in s._schema(c,kind):
                    for name in names:
                        if name not in model._fields:continue
                        if model._fields[name].type=='many2many':data[name]=request.httprequest.form.getlist(name)
                        if model._fields[name].type=='boolean':data[name]=post.get(name,'0')
                r=s._save(c,kind,data)
            return request.redirect(self._url(kind,r.id,company_id=c.id,notice=_('Saved.')))
        except (AccessError,UserError,ValidationError) as exc:
            values=self._detail_values(s,c,kind,ident,str(exc))
            for group,items in values['groups']:
                for item in items:
                    if item['name'] in post:item['value']=post[item['name']]
                    if item['type']=='many2many':item['value']=[int(v) for v in request.httprequest.form.getlist(item['name']) if str(v).isdigit()]
                    if item['type']=='boolean':item['value']=post.get(item['name'])=='1'
            return request.render(PREFIX+'detail',values)

    @http.route(BASE+'/<string:kind>/<int:ident>/action',type='http',auth='user',website=True,methods=['POST'],csrf=True)
    def action(self,kind,ident,**post):
        s=self._service();c=s._company(post.get('company_id'))
        try:
            with request.env.cr.savepoint():s._act(c,kind,ident,post.get('operation'),post)
            notice=_('Operation completed.')
        except (AccessError,UserError,ValidationError) as exc:notice=str(exc)
        return request.redirect(self._url(kind,ident,company_id=c.id,notice=notice))

    @http.route(BASE+'/<string:kind>/<int:ident>/line',type='http',auth='user',website=True,methods=['POST'],csrf=True)
    def line(self,kind,ident,**post):
        s=self._service();c=s._company(post.get('company_id'))
        try:
            with request.env.cr.savepoint():s._line_save(c,kind,ident,post)
            notice=_('Adjustment saved. Recompute the payslip after changing inputs.') if kind=='payslips' else _('Adjustment saved.')
        except (AccessError,UserError,ValidationError) as exc:notice=str(exc)
        return request.redirect(self._url(kind,ident,company_id=c.id,notice=notice))

    @http.route(BASE+'/salary-reports/<int:ident>/xlsx',type='http',auth='user',methods=['GET'])
    def report_xlsx(self,ident,company_id=None,**kw):
        s=self._service();c=s._company(company_id);r=s._record(c,'salary-reports',ident);s._report_scope(c,r)
        output=io.BytesIO();book=xlsxwriter.Workbook(output,{'in_memory':True,'strings_to_formulas':False,'strings_to_urls':False});sheet=book.add_worksheet('Salary Report')
        heads=['Employee','Work Location','Basic','Allowances','Worked Hours','Attendance Deductions','Other Deductions','Reimbursements','Estimated Net']
        for col,label in enumerate(heads):sheet.write_string(0,col,label)
        for row,l in enumerate(r.line_ids,1):
            for col,val in enumerate([l.employee_id.name,l.work_location_id.name or '',l.basic_salary,l.total_allowances,l.worked_hours,l.attendance_deduction,l.other_deductions,l.reimbursements,l.net_salary]):
                if isinstance(val,str):sheet.write_string(row,col,val)
                else:sheet.write_number(row,col,float(val or 0))
        sheet.set_column(0,1,26);sheet.set_column(2,8,19);sheet.freeze_panes(1,2);book.close()
        return request.make_response(output.getvalue(),headers=[('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),('Content-Disposition',content_disposition(r.name+'.xlsx')),('Cache-Control','private, no-store')])

    @http.route(BASE+'/<string:kind>/<int:ident>/print',type='http',auth='user',methods=['GET'])
    def print_record(self,kind,ident,company_id=None,**kw):
        s=self._service();c=s._company(company_id);r=s._record(c,kind,ident)
        report_env=s._env(c)
        if kind=='salary-reports':
            s._report_scope(c,r);report=report_env.ref('employee_portal_suite.action_report_salary_summary').sudo()
        elif kind=='payslips':
            report=c.sudo().employee_admin_payslip_report_id or report_env.ref('hr_payroll.action_report_payslip',raise_if_not_found=False)
            if report:report=report.sudo()
            if report and (report.model!='hr.payslip' or report.report_type!='qweb-pdf'):
                raise UserError(_('Select a valid payslip PDF report on the company.'))
            if not report:raise UserError(_('The standard payslip PDF report is unavailable.'))
        else:raise NotFound()
        pdf,_fmt=report_env['ir.actions.report']._render_qweb_pdf(report.id,res_ids=[r.id])
        return request.make_response(pdf,headers=[('Content-Type','application/pdf'),('Content-Disposition',content_disposition((r.name or 'Payslip')+'.pdf')),('Cache-Control','private, no-store')])
