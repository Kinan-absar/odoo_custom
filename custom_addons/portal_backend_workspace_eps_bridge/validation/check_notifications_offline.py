"""Executes the shipped notification methods against controlled in-memory fixtures.
This is NOT an Odoo registry/database/integration test.
"""
import ast
import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
class AccessError(Exception): pass
class UserError(Exception): pass
class FakeModel:
    def sudo(self): return self
class Datetime:
    def __init__(self, *a, **k): pass
    @staticmethod
    def now(): return datetime(2026, 11, 7, 21, 0, 0)
    @staticmethod
    def to_string(value): return value.strftime('%Y-%m-%d %H:%M:%S') if value else False

def translate(s, *args, **kw):
    return s % kw if kw else (s % args if args else s)

odoo=types.ModuleType('odoo');odoo.api=types.SimpleNamespace(model=lambda fn:fn)
odoo.fields=types.SimpleNamespace(**{k:(lambda *a,**kw:None) for k in ('Many2one','Char','Text','Integer','Selection')}, Datetime=Datetime)
odoo.models=types.SimpleNamespace(Model=FakeModel);odoo._=translate
exceptions=types.ModuleType('odoo.exceptions');exceptions.AccessError=AccessError;exceptions.UserError=UserError
sys.modules.update({'odoo':odoo,'odoo.exceptions':exceptions})
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
mod=load('pbw_notice',ROOT/'portal_backend_workspace/models/notifications.py')
bridge=load('pbw_bridge',ROOT/'portal_backend_workspace_eps_bridge/models/notifications.py')

class RS(list):
    def sudo(self): return self
    def filtered(self, rule): return RS([item for item in self if rule(item)]) if callable(rule) else RS([item for item in self if getattr(item,rule)])
    @property
    def ids(self): return [x.id for x in self]
    def write(self, vals):
        for x in self:
            for k,v in vals.items():setattr(x,k,v)
        return True
    def __getitem__(self,key):
        value=super().__getitem__(key)
        return RS(value) if isinstance(key,slice) else value
    def __getattr__(self,key):
        if len(self)==1:return getattr(self[0],key)
        raise AttributeError(key)

class Company:
    def __init__(self,ident):self.id=ident
    def __eq__(self,other):return isinstance(other,Company) and self.id==other.id
    def __hash__(self):return hash(self.id)
class User:
    def __init__(self,ident,roles=(),companies=(),linked=True,active=True,share=True):
        self.id=ident;self.roles=set(roles);self.company_ids=RS(companies);self.company_id=companies[0] if companies else None
        self.employee_id=object() if linked else False;self.active=active;self.share=share;self.name='User '+str(ident)
        self.workspace=any(r.startswith('portal_backend_workspace.') for r in roles)
    def sudo(self):return self
    def with_company(self,company):return self
    def _is_public(self):return False
    def has_group(self,group):return group in self.roles
    def _pbw_has_access(self):return self.active and self.workspace
    def _pbw_workspace_areas(self):return [{'key':r} for r in ('sales','purchase','accounting','hr') if any(x.startswith('portal_backend_workspace.'+r+'__') for x in self.roles)] if self._pbw_has_access() else []
    def __eq__(self,other):return isinstance(other,User) and self.id==other.id
    def __hash__(self):return hash(self.id)
class Record:
    def __init__(self,ident,name,company,**fields):
        self.id=ident;self._name=name;self.company_id=company;self.write_date=Datetime.now();self.display_name='Document '+str(ident);self.live=True
        self.__dict__.update(fields)
    def sudo(self):return self
    def ensure_one(self):pass
    def exists(self):return self if self.live else False
    def __bool__(self):return self.live
class ResourceTable:
    def __init__(self,records):self.records=records
    def sudo(self):return self
    def browse(self,ident):return self.records.get(ident, Record(ident,'none',None,live=False))
class Notice:
    def __init__(self,ident,vals):
        self.id=ident;self.read_at=False;self.create_date=Datetime.now();self.__dict__.update(vals)
class Cursor:
    def __init__(self):self.sql=[]
    def execute(self,*args):self.sql.append(args)
def field_value(row,key):
    val=getattr(row,key)
    return val.id if isinstance(val,(User,Company)) else val
def match(row,domain):
    for key,op,want in domain:
        got=field_value(row,key)
        if op=='=' and got!=want:return False
        if op=='!=' and got==want:return False
        if op=='in' and got not in want:return False
    return True
class Store(mod.WorkspaceNotification):
    def __init__(self,env):self.env=env;self.rows=RS()
    def search(self,domain,order=None,limit=None):
        result=RS(sorted([r for r in self.rows if match(r,domain)],key=lambda r:r.id,reverse=True))
        return result[:limit] if limit else result
    def search_count(self,domain):return len(self.search(domain))
    def create(self,vals):
        row=Notice(len(self.rows)+1,vals);self.rows.append(row);return row
class Gateway:
    def __init__(self,env,user=None,hr=False):self.env=env;self.user=user;self.hr=hr
    def with_user(self,user):return Gateway(self.env,user,self.hr)
    def _actor(self,kind=None):return self.user,{}
    def _company(self,ident):
        found=next((c for c in self.user.company_ids if c.id==ident),None)
        if not found:raise AccessError()
        return found
    def _record(self,company,kind,ident):
        model={'invoices':'account.move','bills':'account.move','refunds':'account.move','journals':'account.move',**{v[0]:k for k,v in mod.HR_NOTIFICATION_KINDS.items()}}[kind]
        rec=self.env[model].browse(ident)
        if not rec.exists() or rec.company_id!=company:raise AccessError()
        if getattr(rec,'denied',False):raise AccessError()
        if not self.hr:
            if not getattr(rec,'journal_allowed',True):raise AccessError()
            if kind=='invoices' and not self.user.has_group('portal_backend_workspace.accounting__group_customer_invoicing'):raise AccessError()
        return rec
class Env:
    def __init__(self,user):self.user=user;self.uid=user.id;self.su=False;self.cr=Cursor();self.models={};self.context={}
    def __getitem__(self,key):return self.models[key]
class Seen(mod.NotificationSeen):
    def __init__(self,env):self.env=env
    def _get_notification_summary(self,user):return {'sales_approval':{'count':5,'new':4},'inbox':{'count':100,'new':99}}
class IntegratedSeen(bridge.WorkspaceEPSNotifications,Seen):pass
class EPS:
    def __init__(self,summary):self.summary=summary
    def sudo(self):return self
    def _get_notification_summary(self,user):return self.summary

class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.co=Company(1);self.other=Company(2)
        self.actor=User(1,[],[self.co],share=False)
        self.approver=User(2,['portal_backend_workspace.sales__group_portal_sales_creator','portal_backend_workspace.sales__group_portal_sales_approver'],[self.co])
        self.creator=User(3,['portal_backend_workspace.sales__group_portal_sales_creator'],[self.co])
        self.env=Env(self.actor);self.store=Store(self.env);self.env.models['pbw.workspace.notification']=self.store
        self.seen=Seen(self.env);self.env.models['pbw.notification.seen']=self.seen
        self.record=Record(10,'sale.order',self.co,pbw_portal_creator_id=self.creator,pbw_portal_submitter_id=self.creator,pbw_order_requester_id=False)
        self.env.models['sale.order']=ResourceTable({10:self.record})
        self.env.models['account.move']=ResourceTable({})
        self.env.models['purchase.order']=ResourceTable({})
        for model in mod.HR_NOTIFICATION_KINDS:self.env.models[model]=ResourceTable({})
        self.env.models['pbw.portal.accounting.service']=Gateway(self.env)
        self.env.models['pbw.employee.admin.gateway']=Gateway(self.env,hr=True)
    def act_as(self,user):self.env.uid=user.id;self.env.user=user
    def emit(self,users=None):self.store._emit(RS(users or [self.approver]),self.record,'sales','Quotation awaiting approval','Review this quotation')
    def test_sale_event_to_eligible_portal_user(self):
        self.emit();self.assertEqual(len(self.store.rows),1);self.assertEqual(self.store.rows[0].user_id,2)
    def test_duplicate_event_is_not_inserted_twice(self):
        self.emit();self.emit();self.assertEqual(len(self.store.rows),1);self.assertEqual(len(self.env.cr.sql),2)
    def test_different_event_identity_keeps_new_event(self):
        self.emit();self.record.write_date=datetime(2026,11,8);self.emit();self.assertEqual(len(self.store.rows),2)
    def test_actor_is_not_notified_for_own_action(self):
        self.act_as(self.approver);self.emit();self.assertEqual(len(self.store.rows),0)
    def test_cross_company_recipient_excluded(self):
        self.approver.company_ids=RS([self.other]);self.emit();self.assertFalse(self.store.rows)
    def test_inactive_recipient_excluded(self):
        self.approver.active=False;self.emit();self.assertFalse(self.store.rows)
    def test_unlinked_portal_sales_user_excluded(self):
        self.approver.employee_id=False;self.emit();self.assertFalse(self.store.rows)
    def test_no_workspace_access_excluded(self):
        self.approver.workspace=False;self.emit();self.assertFalse(self.store.rows)
    def test_sales_creator_cannot_see_another_creator_document(self):
        target=User(4,['portal_backend_workspace.sales__group_portal_sales_creator'],[self.co]);self.emit([target]);self.assertFalse(self.store.rows)
    def test_sales_monitor_can_see_notification(self):
        target=User(4,['portal_backend_workspace.sales__group_portal_sales_monitor'],[self.co]);self.emit([target]);self.assertEqual(len(self.store.rows),1)
    def test_purchase_monitor_is_not_given_drafts(self):
        u=User(4,['portal_backend_workspace.purchase__group_portal_purchase_monitor'],[self.co]);r=Record(11,'purchase.order',self.co,pbw_portal_preparer_id=self.creator,state='draft')
        self.assertFalse(self.store._target_for_user(u,r,'purchase'));r.state='purchase';self.assertTrue(self.store._target_for_user(u,r,'purchase'))
    def test_purchase_approver_can_open_prepared_document(self):
        u=User(4,['portal_backend_workspace.purchase__group_portal_purchase_approver'],[self.co]);r=Record(11,'purchase.order',self.co,pbw_portal_preparer_id=self.creator,state='draft')
        self.assertIn('/purchase/11?',self.store._target_for_user(u,r,'purchase'))
    def test_accounting_uses_journal_scope(self):
        u=User(4,['portal_backend_workspace.accounting__group_approver'],[self.co]);r=Record(12,'account.move',self.co,move_type='in_invoice',journal_allowed=False);self.env['account.move'].records[12]=r
        self.assertFalse(self.store._target_for_user(u,r,'accounting'));r.journal_allowed=True;self.assertIn('/accounting/bills/12?',self.store._target_for_user(u,r,'accounting'))
    def test_customer_invoice_requires_specific_role(self):
        u=User(4,['portal_backend_workspace.accounting__group_approver'],[self.co]);r=Record(12,'account.move',self.co,move_type='out_invoice');self.env['account.move'].records[12]=r
        self.assertFalse(self.store._target_for_user(u,r,'accounting'));u.roles.add('portal_backend_workspace.accounting__group_customer_invoicing');self.assertTrue(self.store._target_for_user(u,r,'accounting'))
    def test_hr_role_does_not_receive_payroll(self):
        u=User(4,['portal_backend_workspace.hr__group_employee_admin'],[self.co]);r=Record(12,'hr.payslip',self.co);self.env['hr.payslip'].records[12]=r
        self.assertFalse(self.store._target_for_user(u,r,'hr'));u.roles.add('portal_backend_workspace.hr__group_payroll_admin');self.assertIn('/hr/payslips/12?',self.store._target_for_user(u,r,'hr'))
    def test_unknown_model_cannot_be_exposed(self):
        self.assertFalse(self.store._target_for_user(self.approver,Record(11,'ir.config_parameter',self.co),'sales'))
    def test_mark_read_is_per_recipient(self):
        self.emit([self.approver,self.creator]);self.act_as(self.approver);own=next(n.id for n in self.store.rows if n.user_id==2);other=next(n.id for n in self.store.rows if n.user_id==3)
        self.store._mark_read(self.approver,own);self.assertTrue(self.store.rows[own-1].read_at);self.assertFalse(self.store.rows[other-1].read_at)
    def test_cannot_mark_someone_elses_notice(self):
        self.emit();self.act_as(self.creator)
        with self.assertRaises(AccessError):self.store._mark_read(self.creator,1)
    def test_cannot_request_someone_elses_snapshot(self):
        self.emit();self.act_as(self.creator)
        with self.assertRaises(AccessError):self.store._unread_snapshot(self.approver)
    def test_role_revocation_hides_old_notice(self):
        self.emit();self.act_as(self.approver);self.approver.roles.clear();self.assertFalse(self.store._visible_records(self.approver))
    def test_company_revocation_hides_old_notice(self):
        self.emit();self.act_as(self.approver);self.approver.company_ids=RS([self.other]);self.assertFalse(self.store._visible_records(self.approver))
    def test_deleted_document_is_hidden(self):
        self.emit();self.act_as(self.approver);self.record.live=False;self.assertFalse(self.store._visible_records(self.approver))
    def test_unsafe_stored_url_is_never_used(self):
        self.emit();self.act_as(self.approver);self.store.rows[0].url='https://evil.invalid/';self.assertTrue(self.store._get_notice(self.approver,1)[1].startswith('/my/workspace/'));self.assertTrue(self.store._unread_snapshot(self.approver)['items'][0]['url'].startswith('/my/workspace/'))
    def test_bad_ids_do_not_accidentally_mark_all(self):
        self.emit();self.act_as(self.approver)
        for value in (0,-1,False,True,'0','01','x',1.1):
            with self.subTest(value=value),self.assertRaises(AccessError):self.store._mark_read(self.approver,value)
        self.assertFalse(self.store.rows[0].read_at)
    def test_read_all_watermark_preserves_new_arrivals(self):
        self.emit();self.record.write_date=datetime(2026,11,8);self.emit();self.act_as(self.approver);self.store._mark_read(self.approver,upto_id=1)
        self.assertTrue(self.store.rows[0].read_at);self.assertFalse(self.store.rows[1].read_at)
    def test_visible_limit_does_not_undercount(self):
        for n in range(25):self.store._emit(RS([self.approver]),self.record,'sales','Event','body',event_token=str(n))
        self.act_as(self.approver);data=self.store._unread_snapshot(self.approver)
        self.assertEqual(data['count'],25);self.assertEqual(len(data['items']),20);self.assertEqual(data['watermark'],25)
    def test_bell_does_not_add_duplicate_approval_summary_count(self):
        self.emit();self.act_as(self.approver);data=self.seen._get_bell_data(self.approver)
        self.assertEqual(data['unread_count'],1);self.assertEqual(data['workspace_summary']['sales_approval']['count'],5)
    def integrated(self,summary):
        self.env.models['portal.report.seen']=EPS(summary);self.seen=IntegratedSeen(self.env)
        return self.seen
    def test_shared_bell_combines_without_copying(self):
        self.emit();self.act_as(self.approver);self.integrated({'er_approval':{'new':2,'label':'ER Approvals','url':'/my/employee/approvals'}})
        data=self.seen._get_bell_data(self.approver);self.assertEqual(data['unread_count'],3);self.assertEqual(len(self.store.rows),1);self.assertEqual(len(data['items']),2)
    def test_eps_only_user_has_no_workspace_history_or_grants(self):
        user=User(5,[],[self.co]);self.act_as(user);self.integrated({'reports':{'new':1,'url':'/my/employee/reports','label':'Reports'}})
        data=self.seen._get_bell_data(user);self.assertEqual(data['unread_count'],1);self.assertFalse(data['history_url']);self.assertFalse(user.workspace)
    def test_read_in_one_view_clears_same_inbox_in_other(self):
        self.emit();self.act_as(self.approver);self.integrated({'reports':{'new':2,'url':'/my/employee/reports','label':'Reports'}})
        self.store._mark_read(self.approver,1);data=self.seen._get_bell_data(self.approver)
        self.assertEqual(data['workspace_unread_count'],0);self.assertEqual(data['unread_count'],2)
    def test_eps_unsafe_urls_are_filtered(self):
        self.act_as(self.approver);self.integrated({str(n):{'new':1,'url':url} for n,url in enumerate(['https://evil.invalid/','//evil.invalid/','javascript:alert(1)','/my/employee/\\evil','/my/employee/\nx','/web','/my/employeeevil'])})
        self.assertFalse(self.seen._external_bell_items(self.approver))
    def test_duplicate_eps_provider_url_is_one_item(self):
        self.act_as(self.approver);self.integrated({'one':{'new':2,'url':'/my/employee/reports'},'two':{'new':2,'url':'/my/employee/reports'}})
        self.assertEqual(self.seen._get_bell_data(self.approver)['unread_count'],2)
    def test_eps_attendance_only_does_not_receive_eps_bell(self):
        self.approver.roles.add('employee_portal_suite.group_attendance_only');self.act_as(self.approver);self.integrated({'reports':{'new':2,'url':'/my/employee/reports'}})
        self.assertFalse(self.seen._external_bell_items(self.approver))
    def test_zero_eps_counts_are_not_displayed(self):
        self.act_as(self.approver);self.integrated({'reports':{'new':0,'url':'/my/employee/reports'}})
        self.assertFalse(self.seen._external_bell_items(self.approver))
    def test_foreign_user_feed_rejected(self):
        with self.assertRaises(AccessError):self.seen._get_bell_data(self.approver)
    def test_no_permissions_feed_rejected(self):
        user=User(9,[],[self.co],linked=False);self.act_as(user)
        with self.assertRaises(AccessError):self.seen._get_bell_data(user)


    def test_hr_event_is_delivered_to_payroll_not_employee_role(self):
        payroll=User(4,['portal_backend_workspace.hr__group_payroll_admin'],[self.co])
        employee=User(5,['portal_backend_workspace.hr__group_employee_admin'],[self.co])
        slip=Record(12,'hr.payslip',self.co);self.env['hr.payslip'].records[12]=slip
        captured=[]
        self.env.ref=lambda xmlid,**kw:(captured.append(xmlid) or types.SimpleNamespace(id=900))
        self.env.models['res.users']=types.SimpleNamespace(sudo=lambda:types.SimpleNamespace(search=lambda d:RS([payroll,employee])))
        self.store._notify_hr_event(slip,'compute',event_token='audit:1')
        self.assertEqual(captured,['portal_backend_workspace.hr__group_payroll_admin'])
        self.assertEqual([row.user_id for row in self.store.rows],[4])
        self.assertIn('Payslip calculated',self.store.rows[0].title)
    def test_hr_event_identity_suppresses_same_audit_twice(self):
        payroll=User(4,['portal_backend_workspace.hr__group_payroll_admin'],[self.co])
        slip=Record(12,'hr.payslip',self.co);self.env['hr.payslip'].records[12]=slip
        self.env.ref=lambda xmlid,**kw:types.SimpleNamespace(id=900)
        self.env.models['res.users']=types.SimpleNamespace(sudo=lambda:types.SimpleNamespace(search=lambda d:RS([payroll])))
        self.store._notify_hr_event(slip,'compute',event_token='audit:1')
        self.store._notify_hr_event(slip,'compute',event_token='audit:1')
        self.assertEqual(len(self.store.rows),1)
    def test_native_hr_installation_without_custom_groups_is_safe(self):
        slip=Record(12,'hr.payslip',self.co)
        self.env.ref=lambda xmlid,**kw:False
        self.store._notify_hr_event(slip,'state')
        self.assertFalse(self.store.rows)
    def test_native_hr_state_changes_emit_once(self):
        tree=ast.parse((ROOT/'portal_backend_workspace/models/hr/notifications.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_status_updates')
        space={'_PBW_HR_GATEWAY_TOKEN':mod._PBW_HR_GATEWAY_TOKEN}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'hr_state_fixture','exec'),space)
        seen=[];self.env.models['pbw.workspace.notification']=types.SimpleNamespace(_notify_hr_event=lambda r,op:seen.append((r.id,op)))
        records=RS([Record(12,'hr.contract',self.co,state='open')]);records.env=self.env
        space['_status_updates'](records,{12:'draft'});self.assertEqual(seen,[(12,'state')])
        space['_status_updates'](records,{12:'open'});self.assertEqual(len(seen),1)
        self.env.context={'pbw_hr_notification_origin':mod._PBW_HR_GATEWAY_TOKEN}
        space['_status_updates'](records,{12:'draft'});self.assertEqual(len(seen),1)
    def test_hr_batch_audits_preserved_without_duplicate_notices(self):
        tree=ast.parse((ROOT/'portal_backend_workspace/models/hr/gateway.py').read_text())
        cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='EmployeeAdminGateway')
        fn=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name=='_audit')
        space={'KINDS':{'payslips':('hr.payslip','Payslips','payroll')},'_PBW_HR_BATCH_TOKEN':mod._PBW_HR_BATCH_TOKEN}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'hr_audit_fixture','exec'),space)
        audits=[];notices=[]
        audit_model=types.SimpleNamespace(create=lambda values:(audits.append(values) or types.SimpleNamespace(id=len(audits))))
        self.env.models['pbw.employee.admin.audit']=audit_model
        self.env.models['pbw.workspace.notification']=types.SimpleNamespace(_notify_hr_event=lambda *a,**k:notices.append(k))
        gateway=types.SimpleNamespace(env=self.env,_actor=lambda role:(self.actor,{}),_env=lambda company:self.env)
        slip=Record(12,'hr.payslip',self.co)
        space['_audit'](gateway,self.co,'payslips',slip,'save');self.assertEqual(len(notices),1)
        self.env.context={'pbw_hr_batch_notification':mod._PBW_HR_BATCH_TOKEN}
        space['_audit'](gateway,self.co,'payslips',slip,'save');self.assertEqual(len(notices),1);self.assertEqual(len(audits),2)

if __name__=='__main__':unittest.main(verbosity=2)
