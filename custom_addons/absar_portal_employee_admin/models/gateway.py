"""Private, whitelisted portal operations; never a generic model/RPC proxy."""
import math
from datetime import datetime, timedelta
import pytz
from html import escape
from odoo import models, fields, _, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.osv import expression

PREFIX='absar_portal_employee_admin.'
KINDS={
 'employees':('hr.employee','Employees','employee'),
 'attendance':('hr.attendance','Attendance','employee'),
 'contracts':('hr.contract','Contracts','payroll'),
 'work-entries':('hr.work.entry','Work Entries','payroll'),
 'payslips':('hr.payslip','Payslips','payroll'),
 'batches':('hr.payslip.run','Payroll Batches','payroll'),
 'salary-reports':('employee.attendance.salary.report','Salary Reports','payroll'),
}
# Only these named fields may be written. Unsupported optional localization
# fields are omitted; no browser-supplied field/model/method is executed.
SCHEMA={
 'employees':[
 ('Employee',['name','job_title','work_email','work_phone','mobile_phone','category_ids']),
 ('Work Information',['department_id','job_id','parent_id','coach_id','work_location_ids','resource_calendar_id']),
 ('Private Information',['private_email','private_phone','private_street','private_city','private_zip','private_country_id','country_id','identification_id','passport_id','birthday','gender','marital','visa_no','visa_expire','permit_no','work_permit_expiration_date']),
 ('Employee Information',['legal_name','registration_number','l10n_sa_employee_code'])],
 'attendance':[('Attendance',['employee_id','check_in','check_out','check_in_project_id'])],
 'contracts':[('Contract',['name','employee_id','date_start','date_end','structure_type_id','department_id','job_id','contract_type_id','wage_on_signature','hr_responsible_id','resource_calendar_id']),('Salary',['wage','l10n_sa_housing_allowance','l10n_sa_transportation_allowance','l10n_sa_other_allowances']),('Work Information',['work_entry_source'])],
 'work-entries':[('Work Entry',['name','employee_id','contract_id','work_entry_type_id','date_start','date_stop'])],
 'payslips':[('Payslip',['name','employee_id','contract_id','struct_id','payslip_run_id','date_from','date_to']),('Other Information',['date','note'])],
 'batches':[('Payroll Batch',['name','date_start','date_end'])],
 'salary-reports':[('Salary Report',['name','date_from','date_to','employee_ids','department_ids','work_location_ids','employee_tag_ids','include_inactive','struct_id'])],
}

class EmployeeAdminCompany(models.Model):
    _inherit='res.company'
    employee_admin_payslip_report_id=fields.Many2one('ir.actions.report',string='Employee Admin Payslip Report',
        domain="[('model','=','hr.payslip'),('report_type','=','qweb-pdf')]",
        help='Optional existing custom payslip PDF report for the Employee Admin portal. Blank uses the standard payroll report.')

class AttendanceReportLink(models.Model):
    _inherit='employee.attendance.salary.report'
    employee_admin_batch_id=fields.Many2one('hr.payslip.run',readonly=True,copy=False,ondelete='set null')

class EmployeeAdminGateway(models.AbstractModel):
    _name='absar.employee.admin.gateway'
    _description='Employee Admin Portal Gateway'

    def _actor(self,role=None):
        user=self.env.user
        roles={r:user.has_group(PREFIX+'group_'+r+'_admin') for r in ('employee','payroll')}
        if (not user.active or user._is_public() or user.has_group('employee_portal_suite.group_attendance_only')
            or not any(user.has_group('employee_portal_suite.group_employee_portal_'+r) for r in ('admin','superadmin'))
            or not any(roles.values()) or (role and not roles[role])):
            raise AccessError(_('Employee Admin access is not assigned to this user.'))
        return user,roles

    def _id(self,value):
        try:
            ident=int(value)
            if isinstance(value,bool) or ident<=0 or str(ident)!=str(value):raise ValueError()
            return ident
        except (ValueError,TypeError):raise ValidationError(_('Invalid record identifier.'))

    def _company(self,ident=None):
        user,roles=self._actor()
        company=self.env['res.company'].sudo().browse(self._id(ident or user.company_id.id)).exists()
        if not company or company not in user.company_ids:raise AccessError(_('Company is not available.'))
        return company

    def _env(self,company):
        return self.with_context(allowed_company_ids=[company.id],force_company=company.id).with_company(company).sudo().env

    def _kind(self,kind):
        if kind not in KINDS:raise AccessError(_('Unknown Employee Admin page.'))
        self._actor(KINDS[kind][2]);return KINDS[kind]

    def _domain(self,company,kind):
        model=self._env(company)[self._kind(kind)[0]]
        domain=[('company_id','=',company.id)] if 'company_id' in model._fields else [('employee_id.company_id','=',company.id)]
        if kind in ('attendance','work-entries','contracts','payslips'):
            domain=expression.AND([domain,[('employee_id.company_id','=',company.id)]])
        return domain

    def _record(self,company,kind,ident):
        model=self._env(company)[self._kind(kind)[0]].with_context(active_test=False)
        rec=model.search(expression.AND([self._domain(company,kind),[('id','=',self._id(ident))]]),limit=1)
        if not rec:raise AccessError(_('This record is not available in this company.'))
        if kind=='payslips':self._payslip_scope(company,rec)
        return rec

    def _lock(self,rec,version):
        rec.flush_recordset(['write_date'])
        self.env.cr.execute('SELECT id FROM '+rec._table+' WHERE id=%s FOR UPDATE',[rec.id])
        rec.invalidate_recordset()
        if not version or version!=str(rec.write_date):raise UserError(_('This record changed. Reload before saving.'))

    def _audit(self,company,kind,rec,operation,detail=''):
        user,roles=self._actor(KINDS[kind][2])
        self._env(company)['absar.employee.admin.audit'].create(dict(actor_id=user.id,company_id=company.id,
            resource=kind,resource_id=rec.id,operation=operation,detail=str(detail)[:2000]))

    def _selection(self,rec,name):return dict(rec._fields[name]._description_selection(rec.env))

    def _relation_domain(self,company,model):
        obj=self._env(company)[model];domain=[]
        if model=='res.users':
            return [('company_ids','in',[company.id]),('active','=',True),('share','=',False)]
        if 'company_id' in obj._fields:
            domain=[('company_id','=',company.id)] if model in ('hr.employee','hr.contract','hr.payslip.run') else ['|',('company_id','=',False),('company_id','=',company.id)]
        if model.startswith('hr.payroll.') and 'country_id' in obj._fields:
            domain=expression.AND([domain,['|',('country_id','=',False),('country_id','=',company.country_id.id)]])
        return domain

    def _relation(self,company,model,ident):
        if not ident:return self._env(company)[model].browse()
        rec=self._env(company)[model].with_context(active_test=False).search(expression.AND([
            self._relation_domain(company,model),[('id','=',self._id(ident))]]),limit=1)
        if not rec:raise AccessError(_('A selected record is not available in this company.'))
        return rec

    def _schema(self,company,kind):
        self._kind(kind)
        result=[(name,list(names)) for name,names in SCHEMA[kind]]
        if kind=='employees' and self._actor()[1]['payroll']:
            result.append(('Salary Report Settings',['eps_overtime_enabled','eps_target_hours']))
        return result

    def _contract_choices(self,company,kind,employee_id):
        self._kind(kind)
        if kind not in ('payslips','work-entries'):raise AccessError(_('Invalid contract selector.'))
        if not employee_id:return []
        employee=self._relation(company,'hr.employee',employee_id)
        contracts=self._env(company)['hr.contract'].with_context(active_test=False).search(
            expression.AND([self._relation_domain(company,'hr.contract'),[('employee_id','=',employee.id)]]),order='id')
        return [(r.id,r.display_name) for r in contracts]

    def _groups(self,company,kind,rec=None):
        model=self._env(company)[self._kind(kind)[0]]
        groups=[]
        schema=self._schema(company,kind)
        defaults=model.default_get([name for group,names in schema for name in names if name in model._fields]) if not rec else {}
        choices_cache={}
        for group,names in schema:
            items=[]
            for name in names:
                if name not in model._fields:continue
                f=model._fields[name]
                if f.readonly and not f.inverse:continue
                value=rec[name] if rec else defaults.get(name,False)
                options=[]
                if f.type in ('many2one','many2many'):
                    if name=='contract_id' and kind in ('payslips','work-entries'):
                        employee_id=rec.employee_id.id if rec else defaults.get('employee_id')
                        options=self._contract_choices(company,kind,employee_id)
                    elif f.comodel_name not in choices_cache:
                        rel=self._env(company)[f.comodel_name].with_context(active_test=False)
                        domain=self._relation_domain(company,f.comodel_name)
                        if name=='payslip_run_id':domain=expression.AND([domain,[('state','in',['draft','verify'])]])
                        choices=rel.search(domain,order='id',limit=1000)
                        choices_cache[f.comodel_name]=[(r.id,r.display_name) for r in choices]
                    if name!='contract_id' or kind not in ('payslips','work-entries'):options=list(choices_cache[f.comodel_name])
                    value=(value.ids if f.type=='many2many' else value.id) if rec else (value if f.type=='many2many' else value or 0)
                    if not isinstance(value,list) and f.type=='many2many':value=[]
                    if name=='payslip_run_id' and rec and value and not self._editable(kind,rec) and not any(opt[0]==value for opt in options):
                        options.append((rec[name].id,rec[name].display_name))
                elif f.type=='html':
                    from odoo.tools import html2plaintext
                    value=html2plaintext(value or '')
                elif f.type=='selection':options=list(self._selection(model,name).items())
                elif f.type=='datetime' and value:
                    dt=fields.Datetime.to_datetime(value)
                    value=fields.Datetime.context_timestamp(self,dt).strftime('%Y-%m-%dT%H:%M:%S')
                elif f.type in ('date',):value=str(value) if value else ''
                elif f.type in ('float','monetary','integer'):value=value or 0
                else:value=value or ''
                items.append(dict(name=name,label=f.string,type=f.type,value=value,options=options,
                                  required=bool(f.required and not f.compute and not (kind=='payslips' and name=='name'))))
            if items:groups.append((group,items))
        return groups

    def _value(self,company,field,value):
        if field.type=='boolean':return str(value).lower() in ('1','true','on')
        if field.type in ('many2one','many2many'):
            if field.type=='many2one':return self._relation(company,field.comodel_name,value).id or False
            if not isinstance(value,list) or len(value)>500:raise ValidationError(_('Invalid selection.'))
            ids=[self._relation(company,field.comodel_name,v).id for v in value if v]
            return [Command.set(ids)]
        if field.type in ('float','monetary','integer'):
            try:
                number=float(value or 0)
                if not math.isfinite(number):raise ValueError()
                if field.type=='integer' and number!=int(number):raise ValueError()
                return int(number) if field.type=='integer' else number
            except (ValueError,TypeError):raise ValidationError(_('Enter a valid number.'))
        if field.type=='date':
            try:return fields.Date.to_date(value) if value else False
            except (ValueError,TypeError):raise ValidationError(_('Enter a valid date.'))
        if field.type=='datetime':
            if not value:return False
            try:
                local=datetime.fromisoformat(str(value))
                if local.tzinfo:raise ValueError()
                tz=pytz.timezone(self.env.user.tz or 'UTC')
                return fields.Datetime.to_string(tz.localize(local,is_dst=None).astimezone(pytz.UTC).replace(tzinfo=None))
            except (ValueError,TypeError,pytz.InvalidTimeError,pytz.UnknownTimeZoneError):raise ValidationError(_('Enter a valid, unambiguous time in your user timezone.'))
        if field.type=='selection':
            if not value:return False
            if value not in dict(field._description_selection(self.env)):raise ValidationError(_('Invalid selection.'))
            return value
        if field.type=='html':return '<p>'+str(escape(str(value or '')[:10000])).replace('\n','<br/>')+'</p>'
        if field.type in ('char','text'):return str(value or '')[:10000] or False
        raise AccessError(_('Unsupported field.'))

    def _editable(self,kind,rec):
        if not rec:return True
        if kind=='employees':return True
        if kind=='attendance':return True
        if kind=='contracts':return rec.state in ('draft','open')
        if kind=='work-entries':return rec.state in ('draft','conflict')
        if kind=='payslips':return rec.state in ('draft','verify') and (not rec.payslip_run_id or rec.payslip_run_id.state in ('draft','verify'))
        if kind=='batches':return rec.state=='draft' and all(s.state in ('draft','verify','cancel') for s in rec.slip_ids)
        if kind=='salary-reports':return not rec.payroll_batch_id and not rec.employee_admin_batch_id
        return False

    def _save(self,company,kind,post):
        model=self._env(company)[self._kind(kind)[0]]
        rec=self._record(company,kind,post['id']) if post.get('id') else model.browse()
        if rec:self._lock(rec,post.get('version'))
        if not self._editable(kind,rec):raise UserError(_('This record is locked.'))
        if rec and kind=='batches':self._batch_scope(company,rec)
        vals={}
        for group,names in self._schema(company,kind):
            for name in names:
                if name not in model._fields or name not in post:continue
                field=model._fields[name]
                if field.readonly and not field.inverse:continue
                vals[name]=self._value(company,field,post[name])
        if not rec and 'company_id' in model._fields:
            company_field=model._fields['company_id']
            if not (company_field.readonly and (company_field.compute or company_field.related)):
                vals['company_id']=company.id
        if kind=='employees' and not str(vals.get('name') or (rec.name if rec else '')).strip():raise ValidationError(_('Employee name is required.'))
        if vals.get('eps_target_hours',0)<0:raise ValidationError(_('Target hours cannot be negative.'))
        employee=self._relation(company,'hr.employee',vals.get('employee_id') or (rec.employee_id.id if rec and 'employee_id' in rec._fields else None))
        if not employee and kind=='work-entries' and vals.get('contract_id'):
            employee=self._relation(company,'hr.contract',vals['contract_id']).employee_id
        if kind in ('attendance','contracts','work-entries','payslips') and not employee:raise ValidationError(_('Choose an employee.'))
        if rec and kind in ('attendance','work-entries','payslips','contracts') and employee!=rec.employee_id:
            raise UserError(_('The employee on an existing record cannot be reassigned. Create a new draft instead.'))
        if kind=='attendance':
            reason=str(post.get('reason') or '').strip()
            if not reason:raise ValidationError(_('Enter the reason for this attendance entry/correction.'))
            if not vals.get('check_in'):raise ValidationError(_('Check-in is required.'))
            if vals.get('check_out') and vals['check_out']<=vals['check_in']:raise ValidationError(_('Check-out must be after check-in.'))
            if not rec and 'manual' in self._selection(model,'in_mode'):vals['in_mode']='manual'
            if vals.get('check_out') and 'manual' in self._selection(model,'out_mode'):vals['out_mode']='manual'
        if kind in ('contracts','work-entries','payslips','batches','salary-reports'):
            start=vals.get('date_from',vals.get('date_start'))
            end=vals.get('date_to',vals.get('date_end',vals.get('date_stop')))
            if start and end and start>end:raise ValidationError(_('The end must not be before the start.'))
        if kind in ('payslips','work-entries') and 'contract_id' in model._fields:
            contract=self._relation(company,'hr.contract',vals.get('contract_id') or (rec.contract_id.id if rec else False))
            if not contract:
                start=vals.get('date_from',vals.get('date_start'))
                end=vals.get('date_to',vals.get('date_stop'))
                contract=self._auto_contract(company,employee,start,end,kind=='work-entries')
            if not contract:raise ValidationError(_('Choose this employee’s contract.'))
            self.env.cr.execute('SELECT id FROM hr_contract WHERE id=%s FOR UPDATE',[contract.id]);contract.invalidate_recordset()
            if contract.employee_id!=employee or contract.company_id!=company:raise ValidationError(_('Choose this employee’s contract.'))
            vals['contract_id']=contract.id

        if kind=='contracts' and any(vals.get(name,0)<0 for name in ('wage','wage_on_signature')):raise ValidationError(_('Wage cannot be negative.'))
        if kind=='payslips' and not vals.get('struct_id'):
            structure=contract.struct_id if 'struct_id' in contract._fields else False
            if not structure and 'structure_type_id' in contract._fields and contract.structure_type_id:
                typ=contract.structure_type_id
                structure=typ.default_struct_id if 'default_struct_id' in typ._fields else False
            if structure:vals['struct_id']=self._relation(company,'hr.payroll.structure',structure.id).id
            elif not rec or not rec.struct_id:raise ValidationError(_('Choose a salary structure.'))
        if kind=='payslips':
            batch=self._relation(company,'hr.payslip.run',vals.get('payslip_run_id'))
            if batch:
                self.env.cr.execute('SELECT id FROM hr_payslip_run WHERE id=%s FOR UPDATE',[batch.id]);batch.invalidate_recordset()
                if batch.company_id!=company:raise AccessError(_('Payroll batch is not available in this company.'))
                self._batch_scope(company,batch)
                if batch.state not in ('draft','verify'):raise UserError(_('This payroll batch is finalized.'))
                if vals.get('date_from') and vals.get('date_to') and (vals['date_from']<batch.date_start or vals['date_to']>batch.date_end):
                    raise ValidationError(_('Payslip dates must be within the batch period.'))
            if not rec or not rec.credit_note:
                self._no_duplicate_slip(company,employee,vals.get('date_from'),vals.get('date_to'),rec.id if rec else None)
            if not vals.get('name'):
                vals['name']=_('Salary Slip - %s - %s / %s') % (employee.name,vals.get('date_from'),vals.get('date_to'))

        if rec:
            if kind=='batches' and rec.slip_ids:
                if any(name in vals and vals[name]!=rec[name] for name in ('date_start','date_end')):raise UserError(_('Batch dates cannot change once payslips exist.'))
            if kind=='salary-reports' and rec.line_ids:
                raise UserError(_('Create another report to change its filters or period after generation. Existing adjustments are retained.'))
            if kind=='payslips' and rec.state=='verify':vals['state']='draft'
            rec.write(vals)
        else:rec=model.create(vals)
        self._audit(company,kind,rec,'save',', '.join(sorted(vals))+(' | '+reason[:1000] if kind=='attendance' else ''))
        return rec

    def _auto_contract(self,company,employee,start,end,is_datetime=False):
        if not start or not end:return self._env(company)['hr.contract'].browse()
        if is_datetime:
            start=fields.Datetime.context_timestamp(self,fields.Datetime.to_datetime(start)).date()
            end=fields.Datetime.context_timestamp(self,fields.Datetime.to_datetime(end)).date()
        matches=self._env(company)['hr.contract'].search([
            ('company_id','=',company.id),('employee_id','=',employee.id),('state','in',['open','close']),
            ('date_start','<=',start),'|',('date_end','=',False),('date_end','>=',end)],order='date_start desc,id desc',limit=2)
        if len(matches)>1:raise ValidationError(_('More than one contract covers this period. Choose the correct contract.'))
        return matches

    def _no_duplicate_slip(self,company,employee,start,end,exclude_id=None):
        if not start or not end:raise ValidationError(_('Choose a payslip period.'))
        self.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE',[employee.id])
        domain=[('company_id','=',company.id),('employee_id','=',employee.id),('state','!=','cancel'),('credit_note','=',False),('date_from','<=',end),('date_to','>=',start)]
        if exclude_id:domain.append(('id','!=',exclude_id))
        if self._env(company)['hr.payslip'].search_count(domain):
            raise UserError(_('A non-cancelled payslip overlaps this employee’s period. Review the existing payslip.'))

    def _payslip_scope(self,company,slip):
        if 'contract_id' in slip._fields and (not slip.contract_id or slip.contract_id.company_id!=company or slip.contract_id.employee_id!=slip.employee_id):
            raise AccessError(_('The payslip contract does not match its employee/company.'))

    def _batch_scope(self,company,batch):
        if any(slip.company_id!=company or slip.employee_id.company_id!=company for slip in batch.slip_ids):
            raise AccessError(_('Payroll batch contains a payslip from another company.'))
        for slip in batch.slip_ids:self._payslip_scope(company,slip)

    def _batch_candidates(self,company,batch,structure_id=None,tag_ids=None):
        self._kind('batches');self._batch_scope(company,batch)
        if batch.state!='draft':raise UserError(_('Generate payslips only in a new draft batch.'))
        if not batch.date_start or not batch.date_end or batch.date_start>batch.date_end:
            raise ValidationError(_('Save a valid batch period first.'))
        structure=self._relation(company,'hr.payroll.structure',structure_id)
        tags=[self._relation(company,'hr.employee.category',tag).id for tag in (tag_ids or [])]
        domain=[('company_id','=',company.id),('active','=',True)]
        if tags:domain.append(('category_ids','in',tags))
        employees=self._env(company)['hr.employee'].search(domain,order='name,id')
        contracts_domain=[('company_id','=',company.id),('employee_id','in',employees.ids),
            ('state','in',['open','close']),('date_start','<=',batch.date_end),
            '|',('date_end','=',False),('date_end','>=',batch.date_start)]
        contracts=self._env(company)['hr.contract'].search(contracts_domain,order='id')
        by_employee={}
        for contract in contracts:by_employee.setdefault(contract.employee_id.id,[]).append(contract)
        occupied=set(self._env(company)['hr.payslip'].search([
            ('company_id','=',company.id),('employee_id','in',employees.ids),('state','!=','cancel'),
            ('credit_note','=',False),('date_from','<=',batch.date_end),('date_to','>=',batch.date_start)]).mapped('employee_id').ids)
        eligible=[]
        for employee in employees:
            matching=by_employee.get(employee.id,[])
            if employee.id in occupied or len(matching)!=1:continue
            contract=matching[0]
            if structure and 'type_id' in structure._fields and structure.type_id and 'structure_type_id' in contract._fields:
                if contract.structure_type_id!=structure.type_id:continue
            eligible.append((employee,contract))
        return structure,eligible

    def _generate_batch(self,company,ident,post,employee_ids,tag_ids):
        batch=self._record(company,'batches',ident);self._lock(batch,post.get('version'))
        if not employee_ids or len(employee_ids)>500:raise ValidationError(_('Select between 1 and 500 employees.'))
        ids=sorted({self._id(value) for value in employee_ids})
        # Lock employee rows before checking overlaps again, including concurrent requests.
        for ident in ids:
            employee=self._relation(company,'hr.employee',ident)
            self.env.cr.execute('SELECT id FROM hr_employee WHERE id=%s FOR UPDATE',[employee.id])
        structure,candidates=self._batch_candidates(company,batch,post.get('struct_id'),tag_ids)
        allowed={employee.id:contract for employee,contract in candidates}
        if any(ident not in allowed for ident in ids):
            raise ValidationError(_('The selection changed. Refresh employees: each needs one contract active during the period, matching filters, and no overlapping payslip.'))
        for ident in ids:
            data=dict(employee_id=ident,contract_id=allowed[ident].id,payslip_run_id=batch.id,
                date_from=str(batch.date_start),date_to=str(batch.date_end))
            if structure:data['struct_id']=structure.id
            slip=self._save(company,'payslips',data)
            self._native(slip,'compute_sheet')
        if 'verify' in self._selection(batch,'state'):batch.write({'state':'verify'})
        batch.write({'write_date':fields.Datetime.now()})
        self._audit(company,'batches',batch,'generate-payslips','Employees: '+', '.join(map(str,ids)))
        return len(ids)

    def _report_scope(self,company,report):
        for line in report.line_ids:
            if line.employee_id.company_id!=company or (line.company_id and line.company_id!=company):raise AccessError(_('Salary report contains an employee from another company.'))
            if line.contract_id:
                contract=self._relation(company,'hr.contract',line.contract_id)
                if contract.employee_id!=line.employee_id:raise AccessError(_('Report contract does not match the employee.'))

    def _native(self,rec,name):
        if name not in ('compute_sheet','action_payslip_done','action_payslip_cancel','action_validate'):
            raise AccessError(_('Unsupported native operation.'))
        method=getattr(rec,name,None)
        if not callable(method):raise UserError(_('This installed Odoo version does not expose the required operation: %s') % name)
        result=method()
        if isinstance(result,dict) and result.get('type')=='ir.actions.act_window':
            raise UserError(_('Odoo requires an additional native wizard for this operation. Complete it in the backend.'))
        return result

    def _act(self,company,kind,ident,operation,post):
        rec=self._record(company,kind,ident);self._lock(rec,post.get('version'))
        if kind=='attendance' and operation=='resolve':rec.action_resolve_attendance_exception()
        elif kind=='contracts' and operation in ('start','close'):
            if operation=='start' and rec.state!='draft':raise UserError(_('Only draft contracts can be started.'))
            if operation=='close' and rec.state!='open':raise UserError(_('Only running contracts can be closed.'))
            rec.write({'state':'open' if operation=='start' else 'close'})
        elif kind=='work-entries' and operation=='validate':
            if rec.state not in ('draft','conflict'):raise UserError(_('Work entry is already processed.'))
            self._native(rec,'action_validate')
        elif kind=='payslips' and operation in ('compute','validate','cancel'):
            if not self._editable(kind,rec):raise UserError(_('Finalized payslips or batches are locked.'))
            if operation=='compute':result=self._native(rec,'compute_sheet')
            elif operation=='validate':
                if rec.state!='verify':raise UserError(_('Compute and review the payslip first.'))
                if post.get('confirm_action')!='1':raise UserError(_('Confirm that you reviewed this payslip before validation.'))
                result=self._native(rec,'action_payslip_done')
            else:result=self._native(rec,'action_payslip_cancel')
        elif kind=='batches' and operation in ('compute-batch','validate-batch'):
            self._batch_scope(company,rec)
            if rec.state not in ('draft','verify'):raise UserError(_('This batch is finalized.'))
            slips=rec.slip_ids.filtered(lambda item:item.state in ('draft','verify')).sorted('id')
            if not slips:raise UserError(_('No editable payslips remain in this batch.'))
            for slip in slips:
                slip.flush_recordset(['write_date'])
                self.env.cr.execute('SELECT id FROM hr_payslip WHERE id=%s FOR UPDATE',[slip.id])
                slip.invalidate_recordset()
            self._batch_scope(company,rec)
            if any(slip.payslip_run_id!=rec for slip in slips):raise UserError(_('A payslip moved to another batch. Reload.'))
            if any(slip.state not in ('draft','verify') for slip in slips):raise UserError(_('A payslip changed. Reload this batch.'))
            if operation=='validate-batch':
                if post.get('confirm_action')!='1':raise UserError(_('Confirm that all payslips were reviewed.'))
                if any(slip.state!='verify' for slip in slips):raise UserError(_('Compute all draft payslips first.'))
            for slip in slips:self._native(slip,'compute_sheet' if operation=='compute-batch' else 'action_payslip_done')
            rec.write({'write_date':fields.Datetime.now()})
        elif kind=='salary-reports' and operation in ('generate','create-batch'):

            if not self._editable(kind,rec):raise UserError(_('A payroll batch already exists for this report.'))
            if operation=='generate':
                if rec.line_ids:raise UserError(_('This report is already generated. Create another report to regenerate without losing adjustments.'))
                rec.action_generate();self._report_scope(company,rec)
            else:
                self._report_scope(company,rec)
                if not rec.line_ids:raise UserError(_('Generate the salary report first.'))
                for line in rec.line_ids.sorted(lambda item:item.employee_id.id):
                    if not line.contract_id:raise UserError(_('Every employee needs a contract before creating payroll.'))
                    self._no_duplicate_slip(company,line.employee_id,rec.date_from,rec.date_to)
                action=rec.action_create_payroll_batch()
                batch=self._relation(company,'hr.payslip.run',action.get('res_id'))
                if not batch:raise UserError(_('Odoo did not return a payroll batch.'))
                rec.write({'employee_admin_batch_id':batch.id})
        else:raise AccessError(_('This operation is not available.'))
        self._audit(company,kind,rec,operation)
        return rec

    def _line_save(self,company,kind,ident,post):
        rec=self._record(company,kind,ident);self._lock(rec,post.get('version'))
        if not self._editable(kind,rec):raise UserError(_('This record is locked.'))
        if kind=='salary-reports':
            self._report_scope(company,rec)
            line=rec.line_ids.filtered(lambda line:line.id==self._id(post.get('line_id')))
            if not line:raise AccessError(_('This salary line does not belong to this report.'))
            vals={name:self._value(company,line._fields[name],post.get(name,0)) for name in ('manual_absent_days','other_deductions','reimbursements')}
            if any(v<0 for v in vals.values()):raise ValidationError(_('Adjustments cannot be negative.'))
            line.write(vals)
        elif kind=='payslips':
            if post.get('line_id'):
                line=rec.input_line_ids.filtered(lambda line:line.id==self._id(post['line_id']))
                if not line:raise AccessError(_('This input does not belong to this payslip.'))
            else:line=self._env(company)['hr.payslip.input'].browse()
            typ=self._relation(company,'hr.payslip.input.type',post.get('input_type_id'))
            if not typ:raise ValidationError(_('Choose an input type.'))
            amount=self._value(company,self._env(company)['hr.payslip.input']._fields['amount'],post.get('amount'))
            vals={'input_type_id':typ.id,'amount':amount,'name':str(post.get('name') or typ.name)[:250]}
            if line:line.write(vals)
            else:self._env(company)['hr.payslip.input'].create(dict(vals,payslip_id=rec.id))
        else:raise AccessError(_('Line editing is not available.'))
        # Child writes invalidate this form's optimistic snapshot too.
        snapshot={'write_date':fields.Datetime.now()}
        if kind=='payslips' and rec.state=='verify':snapshot['state']='draft'
        rec.write(snapshot)
        self._audit(company,kind,rec,'line adjustment')
        return rec

    def _list(self,company,kind,query='',state='',employee_id=None,page=1,date_from='',date_to=''):
        model=self._env(company)[self._kind(kind)[0]].with_context(active_test=False)
        domain=self._domain(company,kind)
        if query:
            names=['name','work_email','department_id.name','work_location_ids.name','job_title'] if kind=='employees' else (['employee_id.name','check_in_project_id.name'] if kind=='attendance' else ['name']+(['employee_id.name'] if 'employee_id' in model._fields else []))
            domain=expression.AND([domain,expression.OR([[(name,'ilike',str(query)[:120])] for name in names])])
        if employee_id and 'employee_id' in model._fields:
            employee=self._relation(company,'hr.employee',employee_id);domain.append(('employee_id','=',employee.id))
        if kind=='employees':
            if state!='all':domain.append(('active','=',state!='archived'))
        elif kind=='attendance':
            if state=='open':domain.append(('check_out','=',False))
            elif state=='exceptions':domain += [('attendance_exception_state','=','pending'),'|',('auto_checked_out','=',True),('checkout_outside_location','=',True)]
        elif state and 'state' in model._fields:
            if state not in self._selection(model,'state'):raise ValidationError(_('Invalid status.'))
            domain.append(('state','=',state))
        if kind!='employees' and (date_from or date_to):
            try:
                start=fields.Date.to_date(date_from) if date_from else None
                end=fields.Date.to_date(date_to) if date_to else None
            except (ValueError,TypeError):raise ValidationError(_('Choose valid filter dates.'))
            if start and end and start>end:raise ValidationError(_('Filter end date must not be before start.'))
            if kind in ('attendance','work-entries'):
                first,last=('check_in','check_out') if kind=='attendance' else ('date_start','date_stop')
                field=model._fields[first]
                if start:
                    lower=self._value(company,field,str(start)+'T00:00:00')
                    domain=expression.AND([domain,['|',(last,'=',False),(last,'>=',lower)]])
                if end:
                    upper=self._value(company,field,str(end+timedelta(days=1))+'T00:00:00')
                    domain.append((first,'<',upper))
            else:
                first,last=('date_from','date_to') if kind in ('payslips','salary-reports') else ('date_start','date_end')
                if end:domain.append((first,'<=',end))
                if start:domain=expression.AND([domain,['|',(last,'=',False),(last,'>=',start)]])
        count=model.search_count(domain);pages=max(1,math.ceil(count/30));page=min(max(int(page or 1),1),pages)
        recs=model.search(domain,limit=30,offset=(page-1)*30,order='id desc')
        states=list(self._selection(model,'state').items()) if 'state' in model._fields else []
        if kind=='employees':states=[('active',_('Active')),('archived',_('Archived')),('all',_('All'))]
        if kind=='attendance':states=[('open',_('At Work')),('exceptions',_('Exceptions'))]
        return dict(records=recs,total=count,pages=pages,page=page,states=states)
