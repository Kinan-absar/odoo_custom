"""Actual gateway methods on ORM-shaped fixtures. No live Odoo or payroll engine."""
import importlib.util, sys, types, unittest, math
from pathlib import Path
from datetime import datetime,date
import pytz
ROOT=Path(__file__).resolve().parents[1]
class AccessError(Exception):pass
class UserError(Exception):pass
class ValidationError(Exception):pass
class Field:
    def __init__(self,typ='char',comodel_name=None,selection=(),readonly=False,compute=False,related=False):
        self.type=typ;self.comodel_name=comodel_name;self.selection=selection;self.readonly=readonly;self.compute=compute;self.related=related;self.inverse=False;self.required=False;self.string='Field'
    def _description_selection(self,env):return list(self.selection)
class Dates:
    @staticmethod
    def to_date(v):return date.fromisoformat(v) if isinstance(v,str) else v
class Datetimes:
    @staticmethod
    def now():return datetime(2026,10,24,12,0)
    @staticmethod
    def to_string(v):return v.strftime('%Y-%m-%d %H:%M:%S')
    @staticmethod
    def to_datetime(v):return datetime.fromisoformat(v) if isinstance(v,str) else v
    @staticmethod
    def context_timestamp(s,v):return pytz.UTC.localize(v).astimezone(pytz.timezone(s.env.user.tz or 'UTC'))
odoo=types.ModuleType('odoo');odoo._=lambda s:s;odoo.models=types.SimpleNamespace(Model=object,AbstractModel=object)
odoo.fields=types.SimpleNamespace(Date=Dates,Datetime=Datetimes,Many2one=lambda *a,**k:None,Char=lambda *a,**k:None,Integer=lambda *a,**k:None,Text=lambda *a,**k:None)
odoo.Command=types.SimpleNamespace(set=lambda ids:(6,0,ids))
exc=types.ModuleType('odoo.exceptions');exc.AccessError=AccessError;exc.UserError=UserError;exc.ValidationError=ValidationError
osv=types.ModuleType('odoo.osv');osv.expression=types.SimpleNamespace(AND=lambda ds:sum(ds,[]),OR=lambda ds:['|']*(len(ds)-1)+sum(ds,[]))
sys.modules.update({'odoo':odoo,'odoo.exceptions':exc,'odoo.osv':osv})
spec=importlib.util.spec_from_file_location('gateway',ROOT/'models/gateway.py');gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)

class Records(list):
    @property
    def ids(self):return [r.id for r in self]
    @property
    def id(self):return self[0].id if self else False
    def exists(self):return self
    def sudo(self):return self
    def filtered(self,fn):return Records(r for r in self if fn(r))
    def mapped(self,name):
        values=[getattr(r,name) for r in self]
        if all(isinstance(value,(Rec,Records)) for value in values):
            return Records(record for value in values for record in (value if isinstance(value,Records) else [value]))
        return values
    def sorted(self,key):return Records(sorted(self,key=(lambda r:getattr(r,key)) if isinstance(key,str) else key))
    def __getattr__(self,key):return getattr(self[0],key) if len(self)==1 else False
    def __getitem__(self,key):
        if isinstance(key,str):return getattr(self,key)
        result=super().__getitem__(key);return Records(result) if isinstance(key,slice) else result
    def __eq__(self,other):return self.ids==([other.id] if isinstance(other,Rec) else other.ids if isinstance(other,Records) else other)
    def __ne__(self,other):return not self.__eq__(other)

class Rec:
    def __init__(self,model,ident,**values):
        self.id=ident;self._name=model;self._table=model.replace('.','_');self._fields={};self.write_date='v1';self.calls=[];self.native_result=False;self.__dict__.update(values)
    @property
    def display_name(self):return getattr(self,'name',self._name+' '+str(self.id))
    def __getitem__(self,name):return getattr(self,name)
    def __eq__(self,other):return self.id==other.id if isinstance(other,(Rec,Records)) else False
    def __ne__(self,other):return not self.__eq__(other)
    def __bool__(self):return bool(self.id)
    def sudo(self):return self
    def flush_recordset(self,*args):pass
    def invalidate_recordset(self):pass
    def write(self,vals):self.__dict__.update(vals);self.write_date='v2';self.calls.append(('write',vals))
    def compute_sheet(self):self.calls.append('compute');self.state='verify';return self.native_result
    def action_payslip_done(self):self.calls.append('validate');self.state='done';return self.native_result
    def action_payslip_cancel(self):self.calls.append('cancel');self.state='cancel';return self.native_result
    def action_validate(self):self.calls.append('validate');self.state='validated';return self.native_result
    def action_resolve_attendance_exception(self):self.attendance_exception_state='resolved'
    def action_generate(self):self.calls.append('generate');self.line_ids=Records([]);self.state='generated'

class User(Rec):
    def has_group(self,name):return name in self.groups
    def _is_public(self):return self.public
class Cursor:
    def __init__(self):self.calls=[]
    def execute(self,sql,params):self.calls.append((sql,params))
def get(rec,path):
    for part in path.split('.'):
        rec=getattr(rec,part,False)
        if rec is False:return False
    return rec.id if isinstance(rec,(Rec,Records)) else rec

def matches(rec,domain):
    it=iter(domain)
    def take(token):
        if token=='|':
            a=take(next(it));b=take(next(it));return a or b
        if token=='&':
            a=take(next(it));b=take(next(it));return a and b
        name,op,wanted=token;v=get(rec,name)
        if op=='=':return v==wanted
        if op=='!=':return v!=wanted
        if op=='in':return any(item in wanted for item in v) if isinstance(v,list) else v in wanted
        if v is False:return False
        if op=='<':return v<wanted
        if op=='<=':return v<=wanted
        if op=='>=':return v>=wanted
        if op=='ilike':return wanted.lower() in str(v).lower()
        raise AssertionError(op)
    result=[]
    for token in it:result.append(take(token))
    return all(result)
class Model:
    def __init__(self,name,env,fields=None,rows=()):self._name=name;self.env=env;self._fields=fields or {};self.rows=list(rows);self.queries=[]
    def sudo(self):return self
    def with_context(self,**kw):return self
    def browse(self,ident=None):return Records(r for r in self.rows if r.id==ident) if ident else Records()
    def search(self,domain,**kw):
        self.queries.append(domain);rows=Records(r for r in self.rows if matches(r,domain));return rows[:kw.get('limit',len(rows))]
    def search_count(self,domain):return len(self.search(domain))
    def default_get(self,names):return {}
    def create(self,vals):
        vals=dict(vals)
        for key,f in self._fields.items():
            if key in vals and f.type=='many2one' and vals[key]:vals[key]=self.env[f.comodel_name].browse(vals[key])
        rec=Rec(self._name,len(self.rows)+100,**vals);rec._fields=self._fields;self.rows.append(rec);return Records([rec])
class Env(dict):pass
ADMIN='employee_portal_suite.group_employee_portal_admin';SUPER='employee_portal_suite.group_employee_portal_superadmin'
HR=gateway.PREFIX+'group_employee_admin';PAY=gateway.PREFIX+'group_payroll_admin'
class Tests(unittest.TestCase):
    def setUp(self):
        self.c=Rec('res.company',1,country_id=Rec('res.country',1));self.foreign=Rec('res.company',2)
        self.u=User('res.users',10,active=True,public=False,groups={ADMIN,HR,PAY},company_id=self.c,company_ids=Records([self.c]),tz='Asia/Riyadh')
        self.env=Env();self.env.user=self.u;self.env.cr=Cursor()
        self.env['res.company']=Model('res.company',self.env,rows=[self.c,self.foreign])
        self.emp=Rec('hr.employee',3,company_id=self.c,name='Employee',active=True)
        self.other=Rec('hr.employee',4,company_id=self.foreign,name='Foreign Employee')
        employee_fields={'company_id':Field('many2one','res.company'),'name':Field(),'work_email':Field(),'eps_target_hours':Field('float'),'eps_overtime_enabled':Field('boolean'),'groups_id':Field('many2many','res.groups')}
        for rec in (self.emp,self.other):rec._fields=employee_fields
        self.env['hr.employee']=Model('hr.employee',self.env,employee_fields,[self.emp,self.other])
        self.env['absar.employee.admin.audit']=Model('absar.employee.admin.audit',self.env)
        self.slip=Rec('hr.payslip',20,company_id=self.c,employee_id=self.emp,state='draft',credit_note=False,date_from=date(2026,10,1),date_to=date(2026,10,31),payslip_run_id=Records())
        self.slip._fields={'company_id':Field('many2one','res.company'),'employee_id':Field('many2one','hr.employee'),'state':Field('selection',selection=[('draft','Draft'),('verify','Waiting'),('done','Done')])}
        self.env['hr.payslip']=Model('hr.payslip',self.env,self.slip._fields,[self.slip])
        self.s=gateway.EmployeeAdminGateway();self.s.env=self.env;self.s._env=lambda company:self.env
    def test_employee_contract_and_open_batch_options(self):
        colleague=Rec('hr.employee',5,company_id=self.c,name='Colleague')
        self.env['hr.employee'].rows.append(colleague)
        contracts=[Rec('hr.contract',41,company_id=self.c,employee_id=self.emp),
                   Rec('hr.contract',42,company_id=self.c,employee_id=colleague),
                   Rec('hr.contract',43,company_id=self.foreign,employee_id=self.emp)]
        self.env['hr.contract']=Model('hr.contract',self.env,{'company_id':Field('many2one','res.company')},contracts)
        self.assertEqual(self.s._contract_choices(self.c,'payslips',self.emp.id),[(41,contracts[0].display_name)])
        self.assertEqual(self.s._contract_choices(self.c,'work-entries',colleague.id),[(42,contracts[1].display_name)])
        self.assertEqual(self.s._contract_choices(self.c,'payslips',None),[])
        with self.assertRaises(AccessError):self.s._contract_choices(self.c,'payslips',self.other.id)
        with self.assertRaises(AccessError):self.s._contract_choices(self.c,'employees',self.emp.id)
        self.u.groups.remove(PAY)
        with self.assertRaises(AccessError):self.s._contract_choices(self.c,'payslips',self.emp.id)
        self.u.groups.add(PAY)
        batches=[Rec('hr.payslip.run',50+i,company_id=company,state=state) for i,(company,state) in enumerate([
            (self.c,'draft'),(self.c,'verify'),(self.c,'close'),(self.c,'paid'),(self.foreign,'draft')])]
        self.env['hr.payslip.run']=Model('hr.payslip.run',self.env,{'company_id':Field('many2one','res.company')},batches)
        self.env['hr.payslip']._fields.update(contract_id=Field('many2one','hr.contract'),payslip_run_id=Field('many2one','hr.payslip.run'))
        items={item['name']:item for group,rows in self.s._groups(self.c,'payslips') for item in rows}
        self.assertEqual(items['contract_id']['options'],[])
        self.assertEqual([opt[0] for opt in items['payslip_run_id']['options']],[50,51])
        self.slip.contract_id=Records([contracts[0]])
        items={item['name']:item for group,rows in self.s._groups(self.c,'payslips',self.slip) for item in rows}
        self.assertEqual([opt[0] for opt in items['contract_id']['options']],[41])

    def setup_generation(self):
        self.env['hr.payslip'].rows=[]
        self.typ=Rec('hr.payroll.structure.type',91)
        self.structure=Rec('hr.payroll.structure',90,type_id=self.typ)
        self.structure._fields={'type_id':Field('many2one','hr.payroll.structure.type')}
        self.env['hr.payroll.structure']=Model('hr.payroll.structure',self.env,rows=[self.structure])
        self.tag=Rec('hr.employee.category',80)
        self.env['hr.employee.category']=Model('hr.employee.category',self.env,rows=[self.tag])
        self.emp.category_ids=Records([self.tag])
        self.second=Rec('hr.employee',5,company_id=self.c,name='Second',active=True,category_ids=Records())
        self.env['hr.employee'].rows.append(self.second)
        self.contracts=[Rec('hr.contract',60+i,company_id=self.c,employee_id=employee,state='open',
            date_start=date(2026,10,10),date_end=False,structure_type_id=self.typ) for i,employee in enumerate([self.emp,self.second])]
        for contract in self.contracts:contract._fields={'structure_type_id':Field('many2one','hr.payroll.structure.type')}
        self.env['hr.contract']=Model('hr.contract',self.env,rows=self.contracts)
        self.batch=Rec('hr.payslip.run',70,company_id=self.c,state='draft',date_start=date(2026,10,1),date_end=date(2026,10,31),slip_ids=Records())
        self.batch.env=self.env
        self.batch._fields={'company_id':Field('many2one','res.company'),'state':Field('selection',selection=[('draft','New'),('verify','Confirmed')])}
        self.env['hr.payslip.run']=Model('hr.payslip.run',self.env,self.batch._fields,[self.batch])

    def test_batch_generation_candidates(self):
        self.setup_generation()
        _,employees=self.s._batch_candidates(self.c,self.batch,self.structure.id,[])
        self.assertEqual([employee.id for employee,contract in employees],[3,5])
        _,employees=self.s._batch_candidates(self.c,self.batch,self.structure.id,[self.tag.id])
        self.assertEqual([employee.id for employee,contract in employees],[3])
        self.structure.type_id=Rec('hr.payroll.structure.type',92)
        self.assertEqual(self.s._batch_candidates(self.c,self.batch,self.structure.id,[])[1],[])
        self.structure.type_id=self.typ
        self.env['hr.payslip'].rows=[self.slip]
        self.assertEqual([employee.id for employee,contract in self.s._batch_candidates(self.c,self.batch)[1]],[5])
        self.env['hr.contract'].rows.append(self.contracts[1])
        self.assertEqual(self.s._batch_candidates(self.c,self.batch)[1],[])
        self.batch.state='verify'
        with self.assertRaises(UserError):self.s._batch_candidates(self.c,self.batch)

    def test_generate_batch_validation_and_compute(self):
        self.setup_generation();created=[];computed=[]
        def save(company,kind,values):
            self.assertEqual(kind,'payslips');created.append(values)
            slip=Rec('hr.payslip',100+len(created),state='draft');computed.append(slip);return slip
        self.s._save=save
        count=self.s._generate_batch(self.c,self.batch.id,{'version':'v1','struct_id':90},['5','3','3'],[])
        self.assertEqual(count,2)
        self.assertTrue(all(slip.calls==['compute'] for slip in computed))
        self.assertEqual([values['employee_id'] for values in created],[3,5])
        self.assertEqual([values['contract_id'] for values in created],[60,61])
        self.assertTrue(all(values['payslip_run_id']==70 and values['struct_id']==90 and values['date_from']=='2026-10-01' for values in created))
        self.assertEqual(self.batch.state,'verify')
        self.assertEqual(self.env['absar.employee.admin.audit'].rows[-1].operation,'generate-payslips')

    def test_generate_batch_rejects_stale_foreign_and_filters(self):
        self.setup_generation()
        with self.assertRaises(UserError):self.s._generate_batch(self.c,70,{'version':'old'},['3'],[])
        with self.assertRaises(AccessError):self.s._generate_batch(self.c,70,{'version':'v1'},['4'],[])
        with self.assertRaises(ValidationError):self.s._generate_batch(self.c,70,{'version':'v1'},['5'],['80'])
        with self.assertRaises(ValidationError):self.s._generate_batch(self.c,70,{'version':'v1'},[],[])
        self.env['hr.payslip'].rows=[self.slip]
        with self.assertRaises(ValidationError):self.s._generate_batch(self.c,70,{'version':'v1'},['3'],[])
        self.assertEqual(self.env['absar.employee.admin.audit'].rows,[])

    def test_contract_fields_and_hr_responsible_scope(self):
        allowed=Rec('res.users',31,name='HR Responsible',active=True,share=False,company_ids=[2,1])
        foreign=Rec('res.users',32,name='Foreign',active=True,share=False,company_ids=[2])
        portal=Rec('res.users',33,name='Portal',active=True,share=True,company_ids=[1])
        inactive=Rec('res.users',34,name='Inactive',active=False,share=False,company_ids=[1])
        self.env['res.users']=Model('res.users',self.env,{'company_ids':Field('many2many','res.company')},[allowed,foreign,portal,inactive])
        self.env['hr.contract.type']=Model('hr.contract.type',self.env,rows=[Rec('hr.contract.type',9,name='Permanent')])
        self.env['hr.payroll.structure.type']=Model('hr.payroll.structure.type',self.env,rows=[Rec('hr.payroll.structure.type',4,name='KSA Employee')])
        self.env['hr.department']=Model('hr.department',self.env,rows=[])
        self.env['hr.job']=Model('hr.job',self.env,rows=[])
        fields_map={'contract_type_id':Field('many2one','hr.contract.type'),'wage_on_signature':Field('monetary'),
                    'hr_responsible_id':Field('many2one','res.users'),'structure_type_id':Field('many2one','hr.payroll.structure.type'),
                    'department_id':Field('many2one','hr.department'),'job_id':Field('many2one','hr.job')}
        self.env['hr.contract']=Model('hr.contract',self.env,fields_map,[])
        items={item['name']:item for group,rows in self.s._groups(self.c,'contracts') for item in rows}
        self.assertEqual(set(items),set(fields_map));self.assertEqual(items['hr_responsible_id']['options'],[(31,'HR Responsible')])
        self.assertEqual(self.s._value(self.c,fields_map['hr_responsible_id'],'31'),31)
        for ident in ('32','33','34'):
            with self.assertRaises(AccessError):self.s._value(self.c,fields_map['hr_responsible_id'],ident)
    def test_role_matrix(self):
        for groups,employee,payroll in [({ADMIN},False,False),({HR,PAY},False,False),({ADMIN,HR},True,False),({ADMIN,PAY},False,True),({SUPER,HR,PAY},True,True)]:
            self.u.groups=groups
            for role,allowed in [('employee',employee),('payroll',payroll)]:
                if allowed:self.s._actor(role)
                else:
                    with self.assertRaises(AccessError):self.s._actor(role)
        self.u.groups={ADMIN,HR,'employee_portal_suite.group_attendance_only'}
        with self.assertRaises(AccessError):self.s._actor()
    def test_inactive_public(self):
        self.u.active=False
        with self.assertRaises(AccessError):self.s._actor()
        self.u.active=True;self.u.public=True
        with self.assertRaises(AccessError):self.s._actor()
    def test_company_and_record_boundary(self):
        self.assertEqual(self.s._company(1),self.c)
        with self.assertRaises(AccessError):self.s._company(2)
        self.assertEqual(self.s._record(self.c,'employees',3),self.emp)
        with self.assertRaises(AccessError):self.s._record(self.c,'employees',4)
        with self.assertRaises(AccessError):self.s._record(self.c,'account.move',3)
    def test_payroll_hidden_from_hr_role(self):
        self.u.groups={ADMIN,HR}
        self.assertNotIn('Salary Report Settings',[name for name,names in self.s._schema(self.c,'employees')])
        with self.assertRaises(AccessError):self.s._kind('payslips')
    def test_identifier_validation(self):
        for value in (True,0,-1,'1 OR 1=1','1.2','01'):
            with self.assertRaises(ValidationError):self.s._id(value)
    def test_numeric_and_time(self):
        for v in ('NaN','inf','-inf','bad'):
            with self.assertRaises(ValidationError):self.s._value(self.c,Field('float'),v)
        self.assertEqual(self.s._value(self.c,Field('datetime'),'2026-10-24T12:00:00'),'2026-10-24 09:00:00')
        self.u.tz='Europe/Berlin'
        with self.assertRaises(ValidationError):self.s._value(self.c,Field('datetime'),'2026-10-25T02:30:00')
    def test_write_whitelist(self):
        self.u.groups={ADMIN,HR}
        rec=self.s._save(self.c,'employees',{'name':'New Employee','work_email':'work@example.test','eps_target_hours':'999','groups_id':[1],'user_id':1})
        self.assertEqual(rec.name,'New Employee');self.assertFalse(hasattr(rec[0],'groups_id'));self.assertFalse(hasattr(rec[0],'eps_target_hours'));self.assertFalse(hasattr(rec[0],'user_id'))
        self.assertEqual(len(self.env['absar.employee.admin.audit'].rows),1)
    def test_stale_record(self):
        with self.assertRaises(UserError):self.s._save(self.c,'employees',{'id':3,'version':'old','name':'Changed'})
        self.assertEqual(self.emp.name,'Employee')
    def test_payslip_state_and_confirmation(self):
        self.s._act(self.c,'payslips',20,'compute',{'version':'v1'})
        self.assertEqual(self.slip.state,'verify');self.assertNotIn('validate',self.slip.calls)
        with self.assertRaises(UserError):self.s._act(self.c,'payslips',20,'validate',{'version':'v1'})
        self.assertEqual(self.slip.state,'verify')
        self.s._act(self.c,'payslips',20,'validate',{'version':'v1','confirm_action':'1'})
        self.assertEqual(self.slip.state,'done')
        with self.assertRaises(UserError):self.s._act(self.c,'payslips',20,'cancel',{'version':'v1'})
    def test_finalized_batch_lock(self):
        self.slip.payslip_run_id=Records([Rec('hr.payslip.run',1,state='close')])
        self.assertFalse(self.s._editable('payslips',self.slip))
        with self.assertRaises(UserError):self.s._act(self.c,'payslips',20,'compute',{'version':'v1'})
    def test_no_generic_native_method(self):
        with self.assertRaises(AccessError):self.s._native(self.slip,'sudo')
        with self.assertRaises(AccessError):self.s._act(self.c,'payslips',20,'unlink',{'version':'v1'})
    def test_native_wizard_not_bypassed(self):
        self.slip.native_result={'type':'ir.actions.act_window'}
        with self.assertRaises(UserError):self.s._native(self.slip,'compute_sheet')
    def test_duplicate_period_guard(self):
        with self.assertRaises(UserError):self.s._no_duplicate_slip(self.c,self.emp,date(2026,10,10),date(2026,11,1))
        self.s._no_duplicate_slip(self.c,self.emp,date(2026,10,1),date(2026,10,31),20)
        self.s._no_duplicate_slip(self.c,self.emp,date(2026,11,1),date(2026,11,30))
        self.assertTrue(any('hr_employee' in sql and 'FOR UPDATE' in sql for sql,args in self.env.cr.calls))
    def test_foreign_salary_and_batch(self):
        bad=Rec('line',1,employee_id=self.other,company_id=self.foreign,contract_id=0)
        with self.assertRaises(AccessError):self.s._report_scope(self.c,Rec('report',1,line_ids=Records([bad])))
        with self.assertRaises(AccessError):self.s._batch_scope(self.c,Rec('batch',1,slip_ids=Records([Rec('slip',1,company_id=self.foreign,employee_id=self.other)])))
    def test_salary_report_lock(self):
        self.assertFalse(self.s._editable('salary-reports',Rec('report',1,payroll_batch_id='Batch',employee_admin_batch_id=Records())))
    def test_input_parent_boundary(self):
        self.slip.input_line_ids=Records([Rec('hr.payslip.input',44)])
        with self.assertRaises(AccessError):self.s._line_save(self.c,'payslips',20,{'version':'v1','line_id':99,'input_type_id':1,'amount':100})
        self.assertEqual(self.slip.calls,[])

    def test_attendance_reason_and_time(self):
        fields_map={'employee_id':Field('many2one','hr.employee'),'company_id':Field('many2one','res.company'),
            'check_in':Field('datetime'),'check_out':Field('datetime'),
            'in_mode':Field('selection',selection=[('manual','Manual')]),'out_mode':Field('selection',selection=[('manual','Manual')])}
        self.env['hr.attendance']=Model('hr.attendance',self.env,fields_map)
        post={'employee_id':3,'check_in':'2026-10-24T08:00','check_out':'2026-10-24T16:00'}
        with self.assertRaises(ValidationError):self.s._save(self.c,'attendance',post)
        post['reason']='Corrected by manager'
        bad=dict(post,check_out='2026-10-24T07:00')
        with self.assertRaises(ValidationError):self.s._save(self.c,'attendance',bad)
        record=self.s._save(self.c,'attendance',post)
        self.assertEqual(record.check_in,'2026-10-24 05:00:00');self.assertEqual(record.in_mode,'manual')
        self.assertEqual(record.out_mode,'manual')
        self.assertFalse(hasattr(record[0],'check_in_geo_latitude'))
    def test_batch_validation_review(self):
        batch=Rec('hr.payslip.run',40,company_id=self.c,state='draft',slip_ids=Records([self.slip]))
        self.env['hr.payslip.run']=Model('hr.payslip.run',self.env,{'company_id':Field('many2one','res.company')},[batch])
        self.slip.payslip_run_id=Records([batch])
        with self.assertRaises(UserError):self.s._act(self.c,'batches',40,'validate-batch',{'version':'v1','confirm_action':'1'})
        self.s._act(self.c,'batches',40,'compute-batch',{'version':'v1'})
        self.assertEqual(self.slip.state,'verify')
        with self.assertRaises(UserError):self.s._act(self.c,'batches',40,'validate-batch',{'version':'v1','confirm_action':'1'})
        self.s._act(self.c,'batches',40,'validate-batch',{'version':'v2','confirm_action':'1'})
        self.assertEqual(self.slip.state,'done')

    def test_input_change_requires_recompute(self):
        typ=Rec('hr.payslip.input.type',5,name='Reimbursement')
        self.env['hr.payslip.input.type']=Model('hr.payslip.input.type',self.env,rows=[typ])
        fields_map={'amount':Field('float'),'input_type_id':Field('many2one','hr.payslip.input.type')}
        line=Rec('hr.payslip.input',44,name='Existing',amount=10,input_type_id=typ)
        line._fields=fields_map
        self.env['hr.payslip.input']=Model('hr.payslip.input',self.env,fields_map,[line])
        self.slip.input_line_ids=Records([line]);self.slip.state='verify'
        self.s._line_save(self.c,'payslips',20,{'version':'v1','line_id':44,'input_type_id':5,'amount':'25','name':'Changed'})
        self.assertEqual(line.amount,25);self.assertEqual(self.slip.state,'draft')
        with self.assertRaises(UserError):self.s._act(self.c,'payslips',20,'validate',{'version':str(self.slip.write_date),'confirm_action':'1'})

    def test_payslip_contract_boundary(self):
        self.slip._fields['contract_id']=Field('many2one','hr.contract')
        self.slip.contract_id=Rec('hr.contract',8,company_id=self.foreign,employee_id=self.other)
        with self.assertRaises(AccessError):self.s._record(self.c,'payslips',20)
        self.slip.contract_id=Rec('hr.contract',8,company_id=self.c,employee_id=self.emp)
        self.assertEqual(self.s._record(self.c,'payslips',20),self.slip)
    def test_html_notes_are_plain_escaped_text(self):
        result=self.s._value(self.c,Field('html'),'<script>alert(1)</script>')
        self.assertIn('&lt;script&gt;',result);self.assertNotIn('<script>',result)

    def test_form_relation_options_are_scoped(self):
        groups=self.s._groups(self.c,'payslips',self.slip)
        item=next(item for label,items in groups for item in items if item['name']=='employee_id')
        self.assertEqual(item['options'],[(3,'Employee')])
        self.assertEqual(item['value'],3)
    def test_attendance_date_filter_uses_user_timezone(self):
        mapping={'company_id':Field('many2one','res.company'),'employee_id':Field('many2one','hr.employee'),'check_in':Field('datetime'),'check_out':Field('datetime')}
        rows=[Rec('hr.attendance',1,company_id=self.c,employee_id=self.emp,check_in='2026-09-30 22:00:00',check_out='2026-10-01 03:00:00'),
              Rec('hr.attendance',2,company_id=self.c,employee_id=self.emp,check_in='2026-10-31 21:30:00',check_out=False),
              Rec('hr.attendance',3,company_id=self.c,employee_id=self.emp,check_in='2026-09-29 08:00:00',check_out='2026-09-30 10:00:00')]
        self.env['hr.attendance']=Model('hr.attendance',self.env,mapping,rows)
        result=self.s._list(self.c,'attendance',date_from='2026-10-01',date_to='2026-10-31')
        self.assertEqual(result['total'],1);self.assertEqual(result['records'].ids,[1])
        with self.assertRaises(ValidationError):self.s._list(self.c,'attendance',date_from='2026-11-01',date_to='2026-10-01')

class FormPermissionTests(unittest.TestCase):
    def test_website_editor_cannot_disable_admin_forms(self):
        from lxml import etree
        tree=etree.parse(str(ROOT/'views/portal.xml'))
        form=tree.xpath("//form[@data-aea-edit='1']")[0]
        disabled=form.find('fieldset').get('t-att-disabled')
        save=form.xpath(".//button[normalize-space(text())='Save']")[0].get('t-if')
        for kind in gateway.KINDS:
            ctx=dict(kind=kind,rec=False,admin_can_edit=True,editable=False)
            self.assertFalse(bool(eval(disabled,{},ctx)),kind)
            self.assertTrue(bool(eval(save,{},ctx)),kind)
            ctx['admin_can_edit']=False
            self.assertTrue(bool(eval(disabled,{},ctx)),kind)
        self.assertNotIn('editable=',(ROOT/'controllers/portal.py').read_text())
    def test_first_tab_has_nonempty_target(self):
        from lxml import etree
        tree=etree.parse(str(ROOT/'views/portal.xml'))
        tab=tree.xpath("//button[@role='tab']")[0]
        for index in range(4):
            ctx={'group_index':index}
            marker=eval(tab.get('t-att-data-aea-tab'),{},ctx)
            self.assertIsInstance(marker,str)
            self.assertTrue(marker)
            self.assertEqual(marker,eval(tab.get('t-att-aria-controls'),{},ctx))
    def test_archive_not_exposed(self):
        self.assertNotIn("operation in ('archive','restore')",(ROOT/'models/gateway.py').read_text())
        self.assertNotIn("'archive'",(ROOT/'views/portal.xml').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
