"""Run actual submission and edit rules without an Odoo runtime/database."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
class AccessError(Exception):pass
class UserError(Exception):pass
source=Path(__file__).parents[1]/'models'/'accounting.py'
tree=ast.parse(source.read_text())
actor=NS(share=False,name='Issuer',partner_id=NS(id=101),email_formatted='issuer@example.test')
actor.groups={'absar_portal_accounting.group_preparer'}
actor.has_group=lambda name:name in actor.groups
locks=[]
env=NS(uid=1,user=actor,context={},su=True,cr=NS(execute=lambda sql,args:locks.append((sql,args))))
class Base:
    def __init__(self,rows):object.__setattr__(self,'rows',rows)
    def __getattr__(self,key):
        if key=='env':return env
        assert len(self.rows)==1,key
        return self.rows[0][key]
    def __iter__(self):return iter(type(self)([r]) for r in self.rows)
    def __len__(self):return len(self.rows)
    def __eq__(self,other):return isinstance(other,Base) and [id(r) for r in self.rows]==[id(r) for r in other.rows]
    def __contains__(self,other):return any(other==r for r in self)
    def ensure_one(self):assert len(self)==1
    def filtered(self,fn):return type(self)([r.rows[0] for r in self if fn(r)])
    def sorted(self,key):return type(self)(sorted(self.rows,key=lambda r:r[key]))
    def check_access(self,mode):assert mode=='write'
    def sudo(self):return self
    def invalidate_recordset(self):pass
    def write(self,vals):
        vals=dict(vals)
        if isinstance(vals.get('portal_accounting_issuer_id'),int):vals['portal_accounting_issuer_id']=NS(id=vals['portal_accounting_issuer_id'])
        for r in self.rows:r.update(vals)
        return True
    def message_post(self,**kw):self.rows[0]['messages'].append(kw)
    def _portal_accounting_notify_submission(self):self.rows[0]['alerts']+=1
    def _portal_accounting_close_review_activities(self):self.rows[0]['closed']+=1

review=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PortalReview')
names={'write','_portal_accounting_validate_submission','_portal_accounting_reviewer_edit_allowed','_portal_accounting_submit_native','_portal_submission_action'}
methods=[n for n in review.body if isinstance(n,ast.FunctionDef) and n.name in names]
for n in methods:n.decorator_list=[]
node=ast.ClassDef(name='PortalReview',bases=[ast.Name(id='Base',ctx=ast.Load())],keywords=[],body=methods,decorator_list=[])
namespace=dict(Base=Base,AccessError=AccessError,UserError=UserError,_=lambda s:s,_REVIEW_TOKEN=object())
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),namespace)
Review=namespace['PortalReview']
def bill(**patch):
    data=dict(id=1,_table='account_move',_name='account.move',move_type='in_invoice',state='draft',invoice_date=False,
              portal_accounting_review='draft',portal_accounting_review_required=False,portal_accounting_issuer_id=NS(id=1),
              company_id=NS(partner_id=NS(email_formatted=False)),alerts=0,closed=0,messages=[],ref='Vendor reference')
    data.update(patch);return Review([data])
def fail(fn,part):
    try:fn()
    except UserError as exc:assert part in str(exc),(part,str(exc))
    else:raise AssertionError('Expected '+part)
r=bill()
fail(r._portal_accounting_submit_native,'Bill Date')
assert r.portal_accounting_review=='draft' and r.alerts==0 and not r.messages
fail(lambda:r.write({'portal_accounting_review':'submitted'}),'Bill Date')
assert r.portal_accounting_review=='draft'
r.write({'invoice_date':'2026-10-21'})
assert r._portal_accounting_submit_native() is True
assert r.portal_accounting_review=='submitted' and r.alerts==1 and len(r.messages)==1
fail(r._portal_accounting_submit_native,'already awaiting approval')
assert r.alerts==1 and len(r.messages)==1 and len(locks)==3
result=r._portal_submission_action()
assert result['params']['sticky'] is False and result['params']['next']['tag']=='reload'
# Independent native approver may edit the reference while keeping the draft pending.
env.uid=2;actor.groups={'absar_portal_accounting.group_approver'}
assert r._portal_accounting_reviewer_edit_allowed()
r.write({'ref':False})
assert r.portal_accounting_review=='submitted' and r.closed==0
r.write({'invoice_date':False})
fail(r._portal_accounting_validate_submission,'Bill Date')
assert r.portal_accounting_review=='submitted'
r.write({'invoice_date':'2026-10-22'})
r._portal_accounting_validate_submission()
# Same user being issuer or a portal actor may not use the reviewer edit exception.
env.uid=1
assert not r._portal_accounting_reviewer_edit_allowed()
r.write({'ref':'Issuer changed it'})
assert r.portal_accounting_review=='returned' and r.closed==1
env.uid=2;actor.share=True
r.rows[0]['portal_accounting_review']='submitted'
assert not r._portal_accounting_reviewer_edit_allowed()
actor.share=False;actor.groups.add('employee_portal_suite.group_attendance_only')
assert not r._portal_accounting_reviewer_edit_allowed()
actor.groups.remove('employee_portal_suite.group_attendance_only')
r.rows[0]['portal_accounting_review']='approved'
assert not r._portal_accounting_reviewer_edit_allowed()
r.write({'ref':'Changed after approval'})
assert r.portal_accounting_review=='returned'
# Section-independent manual journal entries have no vendor Bill Date requirement.
env.uid=1;actor.groups={'absar_portal_accounting.group_preparer'}
j=bill(move_type='entry')
assert j._portal_accounting_submit_native() is True
# A multi-record submit validates every bill before any state/notification changes.
a=bill(invoice_date='2026-10-21');b=bill(id=2)
batch=Review(a.rows+b.rows)
fail(batch._portal_accounting_submit_native,'Bill Date')
assert a.portal_accounting_review=='draft' and a.alerts==0 and b.alerts==0
print('PASS: required bill date on native submit and transition; duplicate-submit guard/locks; nonsticky toast + reload; approver corrections stay pending; issuer/portal/attendance/approved edits do not bypass review; manual entries; batch prevalidation (ORM fixtures).')
# Exercise real account.move.line hooks, including ORM synchronization during save.
class LineBase:
    def __init__(self,move):self.move_id=move;self.env=env
    def write(self,vals):return True
    def create(self,vals):return self
    def unlink(self):return True
linecls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MoveLine')
linecls.bases=[ast.Name(id='LineBase',ctx=ast.Load())]
linecls.body=[n for n in linecls.body if isinstance(n,ast.FunctionDef)]
for n in linecls.body:n.decorator_list=[]
namespace['LineBase']=LineBase
exec(compile(ast.fix_missing_locations(ast.Module(body=[linecls],type_ignores=[])),str(source),'exec'),namespace)
lines=namespace['MoveLine'](r)
for method,args in [('write',({'debit':150},)),('create',([{'debit':150}],)),('unlink',())]:
    r.rows[0].update(portal_accounting_review='submitted',portal_accounting_review_required=True)
    env.uid=2;actor.groups={'absar_portal_accounting.group_approver'}
    getattr(lines,method)(*args)
    assert r.portal_accounting_review=='submitted',method
    env.uid=1
    getattr(lines,method)(*args)
    assert r.portal_accounting_review=='returned',method
print('PASS: actual journal-line write/create/delete hooks preserve independent approver edits and invalidate issuer edits.')
