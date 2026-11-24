"""Execute changed addon methods on narrow fixtures. Not an Odoo integration test."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree
R=Path(__file__).resolve().parents[1]
P='absar_portal_purchase_monitor.group_portal_purchase_'
class UserError(Exception):pass
class AccessError(Exception):pass
class Forbidden(Exception):pass
TOKEN=object()
ctx={'_':lambda s:s,'UserError':UserError,'AccessError':AccessError,'Forbidden':Forbidden,
     'fields':NS(Datetime=NS(now=lambda:'now')),'PREFIX':P.removesuffix('group_portal_purchase_'),
     '_CONFIRM_TOKEN':TOKEN}
def methods(path,cls,names):
 tree=ast.parse(path.read_text());node=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==cls)
 body=[x for x in node.body if isinstance(x,ast.FunctionDef) and x.name in names]
 for x in body:x.decorator_list=[]
 module=ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name=cls,bases=[],keywords=[],body=body,decorator_list=[])],type_ignores=[]))
 exec(compile(module,str(path),'exec'),ctx);return ctx[cls]
M=methods(R/'models/purchase_order.py','PurchaseOrder',{'_compute_portal_requires_review','_portal_editable','action_absar_portal_approve','action_absar_portal_approve_confirm','action_absar_portal_confirm'})
class User:
 active=True;share=False;employee_id=True;company_id=1;company_ids=[1]
 def __init__(self,id,*roles):self.id=id;self.roles=roles;self.name=str(id)
 def has_group(self,n):return n in [P+role for role in self.roles]
 def sudo(self,*a):return self
 def with_company(self,*a):return self
class Order(M):
 def __init__(self,actor,owner=None,submitter=None,state='draft',review='submitted'):
  self.env=NS(user=actor);self.absar_portal_preparer_id=owner;self.absar_portal_submitter_id=submitter
  self.absar_portal_review_state=review;self.state=state;self.company_id=1;self.name='QA'
  self.absar_portal_approver_id=False;self.absar_portal_working_order=False;self.events=[];self.context={}
 def __iter__(self):return iter([self])
 def sorted(self,*a):return self
 def ensure_one(self):pass
 def _portal_approver(self):
  if not self.env.user.has_group(P+'approver'):raise AccessError('role')
  return self.env.user
 def _portal_lock(self):pass
 def _portal_check_company(self,u):
  if self.company_id not in u.company_ids:raise AccessError('company')
 def sudo(self):return self
 def write(self,v):self.__dict__.update(v);self.events.append('review')
 def with_company(self,c):assert c==self.company_id;return self
 def with_context(self,**k):self.context.update(k);return self
 def button_confirm(self):
  assert self.absar_portal_review_state=='approved'
  assert self.context['_absar_purchase_approval_token'] is TOKEN
  assert self.context['validate_analytic']
  self.events.append('native_confirm');self.state='purchase';return True
 def _portal_close_activities(self):self.events.append('activities')
 def _portal_notify(self,*a):self.events.append('notify')
def deny(fn):
 try:fn()
 except (UserError,AccessError,Forbidden):return
 raise AssertionError('Expected denial')
issuer=User(1,'preparer');reviewer=User(2,'approver');submitter=User(3,'preparer','user','approver')
for method in ('action_absar_portal_approve','action_absar_portal_approve_confirm','action_absar_portal_confirm'):
 for review in ('submitted','approved'):
  o=Order(reviewer,issuer,submitter,review=review)
  assert getattr(o,method)() is True and o.state=='purchase'
  assert o.absar_portal_approver_id==reviewer.id
  assert o.events==['review','native_confirm','activities','notify']
for actor in (issuer,submitter,User(8,'user')):
 deny(lambda actor=actor:Order(actor,issuer,submitter).action_absar_portal_approve())
for state,review in [('purchase','submitted'),('draft','draft'),('draft','returned')]:
 deny(lambda state=state,review=review:Order(reviewer,issuer,state=state,review=review).action_absar_portal_approve())
o=Order(reviewer,issuer);o.company_id=9;deny(o.action_absar_portal_approve)
# Failed native confirmation does not close activities or notify. In Odoo the
# raised exception rolls back the entire request, including review metadata.
o=Order(reviewer,issuer);o.button_confirm=lambda:{'type':'wizard'};deny(o.action_absar_portal_approve)
assert 'activities' not in o.events and 'notify' not in o.events
portal=etree.parse(str(R/'views/portal_purchase_prepare.xml'))
assert len(portal.xpath('//button[@data-action="approve"]'))==1
for old in ('approve_confirm','confirm','work_confirm'):assert not portal.xpath('//button[@data-action="%s"]'%old)
native=etree.parse(str(R/'views/purchase_order_views.xml'))
assert len(native.xpath('//button[@name="action_absar_portal_approve"]'))==1
assert not native.xpath('//button[@name="action_absar_portal_confirm"] | //button[@name="action_absar_portal_approve_confirm"]')
for ident in ('draft_confirm','bid_confirm'):
 assert native.xpath('//xpath[@expr="//button[@id=\'%s\']"]/attribute[@name="invisible"]'%ident)
print('PASS: independent approval, legacy aliases, native-confirm invocation, company/self/state guards, no premature success, single-button UI, both native confirm buttons covered. Fixture checks only; live Odoo upgrade pending.')
