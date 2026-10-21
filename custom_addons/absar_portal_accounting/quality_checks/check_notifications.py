"""Actual notification helpers and write-transition hook, using ORM-shaped fixtures.
No database, mail server or push device is exercised here.
"""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
try:
    from markupsafe import Markup
except ImportError:
    from html import escape
    class Markup(str):
        """Formatting fixture when Odoo's MarkupSafe dependency is unavailable."""
        def __mod__(self, values):
            return Markup(super().__mod__(tuple(escape(str(v), quote=True) for v in values)))

class AccessError(Exception): pass
class UserError(Exception): pass
class Users(list):
    def filtered(self, fn): return Users(u for u in self if fn(u))
    def sudo(self): return self
    @property
    def partner_id(self): return NS(ids=[u.id+100 for u in self])
    def __getitem__(self, key):
        result=super().__getitem__(key)
        return Users(result) if isinstance(key,slice) else result
    def __getattr__(self, key):
        assert len(self)==1
        return getattr(self[0],key)

company=NS(id=1,portal_accounting_journal_ids=[10],partner_id=NS(email_formatted='company@example.test'))
def user(uid, **kw):
    data=dict(id=uid,active=True,share=False,company_ids=[company],employee_id=True,attendance=False,can_write=True,approver=True)
    data.update(kw)
    result=NS(**data)
    result.has_group=lambda group: result.attendance
    result.with_company=lambda co: result
    return result
users=Users([user(1),user(2),user(3,share=True),user(4,share=True,employee_id=False),
             user(5,attendance=True),user(6,can_write=False),user(7,active=False),
             user(8,company_ids=[]),user(9,approver=False)])
class Env:
    uid=1;su=True;context={};user=NS(name='<Preparer>',partner_id=NS(id=101),email_formatted=False)
    def __getitem__(self,key):
        assert key=='res.users'
        return self
    def sudo(self):return self
    def ref(self,key):return NS(id=42)
    def search(self,domain):
        excluded=next(v for k,op,v in domain if k=='id')
        return Users(u for u in users if u.active and u.approver and company in u.company_ids and u.id not in excluded)
    def __contains__(self,key):return False

class Base:
    def write(self,vals):
        for k,v in vals.items():setattr(self,k,v)
        return True

source=Path(__file__).parents[1]/'models'/'accounting.py'
tree=ast.parse(source.read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PortalReview')
selected={'write','_portal_accounting_reviewers','_portal_accounting_path','_portal_accounting_notify','_portal_accounting_notify_submission'}
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in selected]
for n in methods:n.decorator_list=[]
node=ast.ClassDef(name='PortalReview',bases=[ast.Name(id='Base',ctx=ast.Load())],keywords=[],body=methods,decorator_list=[])
namespace=dict(Base=Base,AccessError=AccessError,UserError=UserError,Markup=Markup,_=lambda text:text,_REVIEW_TOKEN=object())
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),namespace)
class Record(namespace['PortalReview']):
    id=40;_name='account.move';move_type='in_invoice';display_name='Draft Bill';journal_id=10
    company_id=company;portal_accounting_issuer_id=NS(id=1);env=Env()
    portal_accounting_review='draft';portal_accounting_review_required=True;state='draft'
    def __iter__(self):return iter([self])
    def filtered(self,fn):return [self] if fn(self) else []
    def ensure_one(self):pass
    def with_user(self,u):
        def check(access):
            assert access=='write'
            if not u.can_write:raise AccessError()
        return NS(check_access=check)
    def sudo(self):return self
    def message_post(self,**kw):self.messages.append(kw)
    def _portal_accounting_close_review_activities(self):self.closed+=1
    def activity_schedule(self,kind,**kw):self.activities.append(kw)

r=Record();r.messages=[];r.activities=[];r.closed=0
assert [u.id for u in r._portal_accounting_reviewers()]==[2,3]
r.write({'portal_accounting_review':'submitted'})
assert len(r.messages)==2 and len(r.activities)==1
assert r.activities[0]['user_id']==2
assert r.messages[0]['partner_ids']==[102] and 'model=account.move' in r.messages[0]['body']
assert r.messages[1]['partner_ids']==[103] and '/my/employee/accounting/bills/40?company_id=1' in r.messages[1]['body']
assert '&lt;Preparer&gt;' in r.messages[0]['body']
r.write({'portal_accounting_comment':'unchanged submission'})
assert len(r.messages)==2 and len(r.activities)==1
r.write({'portal_accounting_review':'returned'})
assert r.closed==2
r.write({'portal_accounting_review':'submitted'})
assert len(r.messages)==4 and len(r.activities)==2
# Company journal scope excludes portal recipients; internal native ACL still governs internal recipients.
r.journal_id=99
assert [u.id for u in r._portal_accounting_reviewers()]==[2]
users[:]=[user(1)]
try:r._portal_accounting_notify_submission()
except UserError:pass
else:raise AssertionError('No independent approver must fail clearly')
print('PASS: actual transition hook, independent company/role/access/employee filters, portal/native links, escaped names, internal activities, duplicate-submit suppression, resubmission, no-approver error.')
