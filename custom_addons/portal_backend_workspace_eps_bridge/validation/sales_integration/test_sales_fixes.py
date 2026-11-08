"""Execute shipped methods with controlled ORM fixtures, NOT a live Odoo registry."""
import ast, copy, json, sys, unittest, os, hashlib
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace as NS
from datetime import datetime, date
class Forbidden(Exception): pass
class NotFound(Exception): pass

ROOT=Path(os.environ.get('PBW_ADDON_PATH', Path(__file__).resolve().parents[3]/'portal_backend_workspace'))
BRIDGE=Path(os.environ.get('PBW_SALES_BRIDGE_PATH', Path(__file__).resolve().parents[2]))
LEGACY_GUARD=Path(__file__).with_name('legacy_sale_guard.py.txt')
PREFIX='portal_backend_workspace.sales__'
TOKEN=object(); LEGACY_TOKEN=object()
class AccessError(Exception):pass
class UserError(Exception):pass
class ValidationError(UserError):pass
class Expr:
 @staticmethod
 def AND(parts):return ('AND',parts)
 @staticmethod
 def OR(parts):return ('OR',parts)
def value(obj, path):
 for k in path.split('.'):
  obj=getattr(obj,k,False)
 return obj

def matches(domain, row):
 if isinstance(domain,tuple) and len(domain)==2 and domain[0] in ('AND','OR'):
  op,parts=domain
  return (all if op=='AND' else any)(matches(x,row) for x in parts)
 it=iter(domain)
 def term(t):
  if t=='|':return term(next(it)) | term(next(it))
  if t=='&':return term(next(it)) & term(next(it))
  if t=='!':return not term(next(it))
  key,op,expect=t;v=value(row,key)
  if hasattr(v,'id') and not hasattr(expect,'id'):v=v.id
  if op=='=':return v==expect
  if op=='!=':return v!=expect
  if op=='in':return v in expect
  if op=='ilike':return str(expect).lower() in str(v or '').lower()
  raise AssertionError(op)
 return all([term(t) for t in it])
class Company:
 def __init__(self,id):self.id=id
class User:
 def __init__(self,id,roles=('creator',),company=None,share=True,active=True,employee=True):
  self.id=id;self.name='User '+str(id);self.active=active;self.share=share
  self.groups={PREFIX+'group_portal_sales_'+r for r in roles}
  if set(roles)&{'approver','user'}:self.groups.add(PREFIX+'group_portal_sales_creator')
  self.company_id=company or COMPANY;self.company_ids=[self.company_id];self.employee_id=employee
  self.partner_id=NS(id=100+id);self.tz='UTC'
 def has_group(self,g):return g in self.groups
 def sudo(self,*args):return self
 def with_company(self,*a):return self
 def __eq__(self,o):return isinstance(o,User) and self.id==o.id
 def __repr__(self):return self.name
COMPANY=Company(1);COMPANY2=Company(2)
USERS={}
class Lines(list):
 @property
 def ids(self):return [x.id for x in self]
 def filtered(self,fn):return Lines([x for x in self if fn(x)])
 def invalidate_recordset(self):pass
class Cursor:
 def __init__(self):self.records=[];self.sql=[]
 def execute(self,*args):self.sql.append(args)
 @contextmanager
 def savepoint(self):
  snapshots=[(r,dict(r)) for r in self.records]
  try:yield
  except Exception:
   for record,snapshot in snapshots:record.clear();record.update(snapshot)
   raise
class Env:
 def __init__(self,user,context=None,su=True,cr=None,registry=None):
  self.user=user;self.uid=user.id;self.context=context or {};self.su=su;self.cr=cr or Cursor();self.registry=registry or {}
 def __getitem__(self,key):return self.registry[key]
class Native:
 def __init__(self,user,owner=None,prepared=None,company=None,state='draft'):
  object.__setattr__(self,'env',Env(user));owner=owner or user
  object.__setattr__(self,'_data',dict(id=10,name='Q010',company_id=company or COMPANY,state=state,
   create_uid=owner,pbw_portal_creator_id=prepared if prepared is not None else owner,
   pbw_portal_submitter_id=False,pbw_portal_review_state='draft',pbw_portal_approver_id=False,
   pbw_order_review_state='none',pbw_order_requester_id=False,pbw_order_approver_id=False,
   pbw_direct_confirmed_by_id=False,pbw_portal_review_note=False,
   absar_portal_creator_id=False,absar_portal_submitter_id=False,absar_order_requester_id=False,
   pbw_project_id=False,construction_project_id=False,_fields={},
   order_line=Lines([NS(id=100,display_type=False,product_uom_qty=1)]),
   confirmations=0,notes=0,closed=0,review_alerts=0,creator_alerts=0,legacy_closed=0,
   native_fail=False,native_fail_after=False,native_silent=False,native_write_allowed=True))
  self.env.cr.records.append(self._data)
 def __getattr__(self,key):
  data=object.__getattribute__(self,'__dict__').get('_data',{})
  if key in data:return data[key]
  raise AttributeError(key)
 def __setattr__(self,key,v):
  if key in ('env','_data'):object.__setattr__(self,key,v)
  else:self._data[key]=v
 def __getitem__(self,key):return getattr(self,key)
 def __setitem__(self,key,v):setattr(self,key,v)
 def __iter__(self):return iter([self] if self.id else [])
 def __len__(self):return 1 if self.id else 0
 def __bool__(self):return bool(self.id)
 def ensure_one(self):assert self.id
 def exists(self):return self
 def filtered(self,pred):
  keep=bool(getattr(self,pred)) if isinstance(pred,str) else pred(self)
  if keep:return self
  empty=copy.copy(self);object.__setattr__(empty,'_data',dict(self._data,id=0));return empty
 def __sub__(self,other):return self.filtered(lambda r: not bool(other))
 def sorted(self,*a):return self
 def _clone(self,**kw):
  r=copy.copy(self);e=copy.copy(self.env)
  for k,v in kw.items():setattr(e,k,v)
  object.__setattr__(r,'env',e);return r
 def sudo(self,flag=True):return self._clone(su=flag)
 def with_context(self,**kw):return self._clone(context={**self.env.context,**kw})
 def with_company(self,*a):return self
 def with_user(self,user):return self._clone(user=user,uid=user.id)
 def check_access(self,operation):
  if not self.native_write_allowed:raise AccessError('Native ACL denied')
 def invalidate_recordset(self):pass
 def write(self,vals):
  for k,v in vals.items():
   if k in ('pbw_portal_creator_id','pbw_portal_submitter_id','pbw_order_requester_id','pbw_portal_approver_id','pbw_order_approver_id','pbw_direct_confirmed_by_id') and v:v=USERS[v]
   if k=='order_line':v=Lines()
   setattr(self,k,v)
  return True
 def action_confirm(self):
  self.confirmations+=1
  if self.native_fail:raise ValidationError('native validation')
  if not self.native_silent:self.write({'state':'sale'})
  if self.native_fail_after:raise ValidationError('native validation after mutation')
  return True
 def message_post(self,**kw):self.notes+=1
 def action_draft(self):self.write({'state':'draft'});return True
 def _absar_portal_close_activities(self):self.legacy_closed+=1

COMMON={'_':lambda s:s,'AccessError':AccessError,'UserError':UserError,'ValidationError':ValidationError,
 '_PREFIX':PREFIX,'_REVIEW_TOKEN':TOKEN,'expression':Expr,'fields':NS(Datetime=NS(now=lambda:datetime(2026,11,7)),Date=NS(to_date=date.fromisoformat)),
 '_REVIEW_FIELDS':{'pbw_order_review_state','pbw_order_requester_id','pbw_order_approver_id','pbw_sales_decision_at','pbw_portal_creator_id','pbw_portal_submitter_id','pbw_portal_review_state','pbw_portal_approver_id','pbw_direct_confirmed_by_id'}}
def load_class(file, cls, base, namespace=None, only=None):
 tree=ast.parse(file.read_text());node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 node=copy.deepcopy(node);node.bases=[ast.Name(id='FixtureParent',ctx=ast.Load())];node.keywords=[]
 node.body=[m for m in node.body if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef)) and (only is None or m.name in only)]
 for m in node.body:m.decorator_list=[]
 ns={**COMMON,'FixtureParent':base,**(namespace or {})}
 exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(file),'exec'),ns)
 return ns[cls]
Core=load_class(ROOT/'models/sales/sale_order.py','SaleOrder',Native)
def with_fixtures(parent):
 class Order(parent):
  def _pbw_portal_notify_reviewers(self,conversion=False):self.review_alerts+=1
  def _pbw_portal_notify_creator(self,message):self.creator_alerts+=1
  def _pbw_portal_close_activities(self):self.closed+=1
 return Order
Order=with_fixtures(Core)
class PartnerBase:pass
Partner=load_class(ROOT/'models/sales/res_partner.py','ResPartner',PartnerBase)
BridgePartner=load_class(BRIDGE/'models/sales_data.py','SalesCustomerDataBridge',Partner)
imports=[]
def importer(name):imports.append(name);return NS(_REVIEW_TOKEN=LEGACY_TOKEN)
Bridge=load_class(BRIDGE/'models/sales_data.py','SalesProjectDataBridge',Core,{'import_module':importer})
BridgeOrder=with_fixtures(Bridge)
def direct_method(file,cls,name,namespace=None):
 loaded=load_class(file,cls,object,namespace,only=[name]);return getattr(loaded,name)

class PolicyTests(unittest.TestCase):
 def setUp(self):
  self.a=User(1);self.b=User(2,('user',));self.ap=User(3,('approver',));self.ap2=User(4,('approver',));self.mon=User(5,('monitor',));self.intern=User(6,(),share=False)
  USERS.update({u.id:u for u in (self.a,self.b,self.ap,self.ap2,self.mon,self.intern)})
 def order(self,user=None,**kw):return Order(user or self.a,**kw)
 def test_preparer_own_can_submit(self):self.assertTrue(self.order()._pbw_review_permissions(self.a)['can_submit'])
 def test_all_documents_cannot_submit_others(self):
  o=self.order(self.b,owner=self.a);self.assertFalse(o._pbw_review_permissions(self.b)['can_submit'])
  with self.assertRaises(UserError):o._pbw_portal_submit()
  self.assertEqual(o.pbw_portal_creator_id,self.a);self.assertEqual(o.review_alerts,0)
 def test_all_documents_can_submit_own(self):
  o=self.order(self.b);o._pbw_portal_submit();self.assertEqual(o.pbw_portal_review_state,'submitted');self.assertEqual(o.review_alerts,1)
 def test_metadata_takeover_does_not_grant_ownership(self):
  o=self.order(self.b,owner=self.a,prepared=self.b)
  self.assertEqual(o._pbw_sales_owner(),self.a)
  with self.assertRaises(UserError):o._pbw_portal_submit()
 def test_salesperson_assignment_does_not_grant_ownership(self):
  o=self.order(self.b,owner=self.a);o.user_id=self.b
  self.assertFalse(o._pbw_review_permissions(self.b)['can_submit'])
 def test_native_own_draft_is_submittable(self):
  o=self.order(self.a,prepared=False);o._pbw_portal_submit()
  self.assertEqual(o.pbw_portal_creator_id,self.a)
 def test_owner_domain_uses_creation_not_salesperson(self):
  self.assertEqual(self.order()._pbw_sales_owner_domain(self.a),[('create_uid','=',1)])
 def test_owner_approver_direct_overrides_implied_prepare(self):
  p=self.order(self.ap)._pbw_review_permissions(self.ap)
  self.assertTrue(p['can_confirm_direct']);self.assertFalse(p['can_submit']);self.assertFalse(p['can_request_order'])
 def test_preparer_cannot_confirm(self):
  with self.assertRaises(AccessError):self.order()._pbw_confirm_own_quotation()
 def test_approver_cannot_direct_confirm_other_creator(self):
  with self.assertRaises(AccessError):self.order(self.ap,owner=self.a)._pbw_confirm_own_quotation()
 def test_approver_direct_confirm_uses_native_and_audits(self):
  o=self.order(self.ap);o._pbw_confirm_own_quotation()
  self.assertEqual(o.state,'sale');self.assertEqual(o.confirmations,1);self.assertEqual(o.pbw_order_review_state,'direct');self.assertEqual(o.pbw_direct_confirmed_by_id,self.ap)
  self.assertFalse(o.pbw_portal_approver_id);self.assertEqual(o.notes,1);self.assertEqual(o.closed,1);self.assertEqual(o.review_alerts,0)
 def test_direct_native_button_path(self):
  o=self.order(self.ap);self.assertTrue(o.action_confirm());self.assertEqual(o.state,'sale')
 def test_public_custom_direct_action(self):
  o=self.order(self.ap);self.assertEqual(o.action_pbw_confirm_own()['tag'],'reload');self.assertEqual(o.state,'sale')
 def test_direct_repeated_confirmation_rejected(self):
  o=self.order(self.ap);o._pbw_confirm_own_quotation()
  with self.assertRaises(AccessError):o._pbw_confirm_own_quotation()
  self.assertEqual(o.confirmations,1)
 def test_raw_portal_rpc_confirmation_not_granted(self):
  o=self.order(self.ap).sudo(False)
  with self.assertRaises(AccessError):o.action_confirm()
  with self.assertRaises(AccessError):o.action_pbw_confirm_own()
 def test_forged_confirmation_token_not_accepted(self):
  o=self.order().with_context(_pbw_sales_confirm_token=True)
  with self.assertRaises(UserError):o.action_confirm()
 def test_forged_direct_metadata_not_accepted(self):
  with self.assertRaises(AccessError):self.order(self.ap).write({'pbw_direct_confirmed_by_id':self.ap.id})
 def test_direct_write_to_sale_still_forbidden(self):
  with self.assertRaises(AccessError):self.order(self.ap).write({'state':'sale'})
 def test_missing_or_invalid_lines_block_confirm(self):
  for lines in ([],[NS(display_type='line_section',product_uom_qty=0)],[NS(display_type=False,product_uom_qty=0)],[NS(display_type=False,product_uom_qty=-1)]):
   with self.subTest(lines=lines):
    o=self.order(self.ap);o.order_line=Lines(lines)
    with self.assertRaises(ValidationError):o._pbw_confirm_own_quotation()
    self.assertEqual(o.state,'draft');self.assertFalse(o.pbw_direct_confirmed_by_id)
 def test_native_validation_failure_rolls_back(self):
  o=self.order(self.ap);o.native_fail=True
  with self.assertRaises(ValidationError):o._pbw_confirm_own_quotation()
  self.assertEqual(o.state,'draft');self.assertFalse(o.pbw_direct_confirmed_by_id);self.assertEqual(o.notes,0)
 def test_partial_native_failure_rolls_back_state_and_metadata(self):
  o=self.order(self.ap);o.native_fail_after=True
  with self.assertRaises(ValidationError):o._pbw_confirm_own_quotation()
  self.assertEqual(o.state,'draft');self.assertEqual(o.confirmations,0);self.assertFalse(o.pbw_direct_confirmed_by_id)
 def test_native_action_not_completing_is_not_claimed_confirmed(self):
  o=self.order(self.ap);o.native_silent=True
  with self.assertRaises(UserError):o._pbw_confirm_own_quotation()
  self.assertFalse(o.pbw_direct_confirmed_by_id)
 def test_inactive_wrong_company_unlinked_are_denied(self):
  for actor in (User(7,('approver',),active=False),User(8,('approver',),company=COMPANY2),User(9,('approver',),employee=False)):
   with self.subTest(actor=actor.id):
    o=self.order(actor,company=COMPANY)
    self.assertFalse(o._pbw_review_permissions(actor)['can_confirm_direct'])
    with self.assertRaises(AccessError):o._pbw_confirm_own_quotation()
 def test_internal_native_acl_not_bypassed(self):
  actor=User(10,('approver',),share=False);USERS[10]=actor;o=self.order(actor);o.native_write_allowed=False
  with self.assertRaises(AccessError):o._pbw_confirm_own_quotation()
 def test_non_draft_states_block_all_confirm(self):
  for state in ('sale','done','cancel'):
   with self.subTest(state=state):
    o=self.order(self.ap,state=state);p=o._pbw_review_permissions(self.ap)
    self.assertFalse(p['can_confirm_direct']);self.assertFalse(p['can_submit'])
 def test_owner_approver_own_pending_can_confirm(self):
  for review in ('draft','returned','submitted','approved'):
   with self.subTest(review=review):
    o=self.order(self.ap);o.pbw_portal_review_state=review
    o._pbw_confirm_own_quotation();self.assertEqual(o.state,'sale')
 def test_other_creator_approval_remains_independent(self):
  o=self.order(self.ap,owner=self.a);o.pbw_portal_review_state='submitted';o.pbw_portal_submitter_id=self.a
  p=o._pbw_review_permissions(self.ap);self.assertTrue(p['can_approve']);self.assertFalse(p['can_confirm_direct']);self.assertFalse(p['can_submit'])
  o.action_pbw_portal_approve();self.assertEqual(o.pbw_portal_approver_id,self.ap);self.assertEqual(o.state,'draft')
 def test_owner_cannot_self_approve_instead_of_direct_confirm(self):
  o=self.order(self.ap);o.pbw_portal_review_state='submitted'
  with self.assertRaises(UserError):o.action_pbw_portal_approve()
 def test_request_conversion_owned_only(self):
  o=self.order(self.b,owner=self.a);o.pbw_portal_review_state='approved';o.pbw_portal_approver_id=self.ap
  with self.assertRaises(UserError):o.action_pbw_request_order()
 def test_independent_conversion_uses_native(self):
  o=self.order(self.ap,owner=self.a);o.pbw_portal_review_state='approved';o.pbw_portal_approver_id=self.ap
  o.pbw_order_review_state='requested';o.pbw_order_requester_id=self.a
  o.action_pbw_approve_order();self.assertEqual(o.state,'sale');self.assertEqual(o.pbw_order_review_state,'approved');self.assertFalse(o.pbw_direct_confirmed_by_id)
 def test_unmanaged_internal_native_order_unchanged(self):
  o=self.order(self.intern,prepared=False);self.assertTrue(o.action_confirm());self.assertEqual(o.state,'sale');self.assertFalse(o.pbw_direct_confirmed_by_id)
 def test_print_directly_confirmed_order(self):
  fn=direct_method(ROOT/'models/sales/report_approval.py','SaleOrderPrintApproval','_pbw_can_print_for')
  o=self.order(self.ap);o._pbw_confirm_own_quotation();self.assertTrue(fn(o,self.b))
 def test_reset_clears_direct_confirmation_metadata(self):
  o=self.order(self.ap);o._pbw_confirm_own_quotation();o.action_draft();self.assertEqual(o.state,'draft');self.assertFalse(o.pbw_direct_confirmed_by_id);self.assertEqual(o.pbw_order_review_state,'none')

class DataBridgeTests(unittest.TestCase):
 def setUp(self):
  self.p=Partner();self.p._fields={}
  self.bp=BridgePartner();self.bp._fields={'absar_is_sales_customer':NS(type='boolean')}
  self.u=User(23,('approver',));self.other=User(24);USERS.update({23:self.u,24:self.other});imports.clear()
 def contact(self,**kw):return NS(active=True,company_id=False,pbw_is_sales_customer=False,absar_is_sales_customer=False,**kw)
 def test_standalone_customer_flag(self):
  c=self.contact();c.pbw_is_sales_customer=True
  self.assertTrue(matches(self.p._pbw_sales_customer_domain(COMPANY),c))
 def test_legacy_flag_not_read_without_bridge(self):
  c=self.contact();c.absar_is_sales_customer=True
  self.assertFalse(matches(self.p._pbw_sales_customer_domain(COMPANY),c))
 def test_bridge_accepts_either_explicit_flag(self):
  for flag in ('pbw_is_sales_customer','absar_is_sales_customer'):
   c=self.contact();setattr(c,flag,True)
   self.assertTrue(matches(self.bp._pbw_sales_customer_domain(COMPANY),c))
 def test_no_customer_rank_fallback(self):
  c=self.contact(customer_rank=99)
  self.assertFalse(matches(self.bp._pbw_sales_customer_domain(COMPANY),c))
 def test_bridge_flags_preserve_company_and_active_scope(self):
  for company,active,expected in ((False,True,True),(COMPANY,True,True),(COMPANY2,True,False),(False,False,False)):
   c=self.contact();c.company_id=company;c.active=active;c.absar_is_sales_customer=True
   self.assertEqual(matches(self.bp._pbw_sales_customer_domain(COMPANY),c),expected)
 def test_missing_legacy_field_falls_back(self):
  self.bp._fields={};self.assertEqual(self.bp._pbw_sales_customer_eligibility_domain(),self.p._pbw_sales_customer_eligibility_domain())
 def test_wrong_type_flag_is_not_used(self):
  self.bp._fields={'absar_is_sales_customer':NS(type='char')};self.assertEqual(self.bp._pbw_sales_customer_eligibility_domain(),self.p._pbw_sales_customer_eligibility_domain())
 def order(self,linked=True):
  o=BridgeOrder(self.u)
  if linked:o._fields={'construction_project_id':NS(type='many2one',comodel_name='project.project')}
  return o
 def test_standalone_project_field(self):self.assertEqual(self.order(False)._pbw_sales_project_field(),'pbw_project_id')
 def test_existing_construction_project_read(self):
  o=self.order();o.construction_project_id=NS(id=11,name='Existing Project');self.assertEqual(o._pbw_sales_project().id,11)
 def test_construction_project_has_precedence(self):
  o=self.order();o.construction_project_id=NS(id=11);o.pbw_project_id=NS(id=12);self.assertEqual(o._pbw_sales_project().id,11)
 def test_prebridge_local_project_is_preserved(self):
  o=self.order();o.pbw_project_id=NS(id=12);self.assertEqual(o._pbw_sales_project().id,12)
 def test_project_save_updates_actual_field(self):
  self.assertEqual(self.order()._pbw_sales_project_values(NS(id=11)),{'construction_project_id':11,'pbw_project_id':False})
 def test_clear_cannot_resurrect_old_local_project(self):
  self.assertEqual(self.order()._pbw_sales_project_values(False),{'construction_project_id':False,'pbw_project_id':False})
 def test_standalone_writes_only_local_field(self):self.assertEqual(self.order(False)._pbw_sales_project_values(NS(id=12)),{'pbw_project_id':12})
 def test_wrong_project_model_ignored(self):
  o=self.order();o._fields['construction_project_id'].comodel_name='res.partner';self.assertEqual(o._pbw_sales_project_field(),'pbw_project_id')
 def test_project_search_matches_display_precedence(self):
  o=self.order();o.construction_project_id=NS(id=11,name='Real Project');o.pbw_project_id=NS(id=12,name='Stale Project')
  self.assertTrue(matches(o._pbw_sales_project_search_domain('Real'),o));self.assertFalse(matches(o._pbw_sales_project_search_domain('Stale'),o))
  o.construction_project_id=False;self.assertTrue(matches(o._pbw_sales_project_search_domain('Stale'),o))
 def test_bridge_no_import_for_standalone_confirmation(self):
  self.assertEqual(self.order()._pbw_native_confirmation_context(),{});self.assertEqual(imports,[])
 def test_bridge_refuses_unauthorized_context(self):
  o=self.order();o.create_uid=self.other
  with self.assertRaises(AccessError):o._pbw_native_confirmation_context()
  self.assertEqual(imports,[])
 def test_legacy_tokens_only_given_after_authorization(self):
  o=self.order();o._fields['absar_portal_creator_id']=NS(type='many2one',comodel_name='res.users')
  o._absar_portal_can_confirm=lambda u:False
  self.assertIs(o._pbw_native_confirmation_context()['_absar_sales_confirm_token'],LEGACY_TOKEN)
  self.assertEqual(imports,['odoo.addons.absar_portal_sales.models.sale_order'])
 def test_authorized_direct_confirmation_coexists_with_real_original_guard(self):
  # Execute both actual guard orders, not a made-up token contract.
  for legacy_first in (False,True):
   with self.subTest(legacy_first=legacy_first):
    leg_ns={'_PREFIX':'absar_portal_sales.','_REVIEW_TOKEN':LEGACY_TOKEN,'_REVIEW_FIELDS':{'absar_portal_review_state','absar_order_review_state'}}
    methods=['action_confirm','write','_absar_portal_can_confirm','_absar_portal_invalidate_review']
    if legacy_first:
     parent=load_class(LEGACY_GUARD,'SaleOrder',Core,leg_ns,methods)
    else:
     legacy=load_class(LEGACY_GUARD,'SaleOrder',Native,leg_ns,methods)
     parent=load_class(ROOT/'models/sales/sale_order.py','SaleOrder',legacy)
    bridge=load_class(BRIDGE/'models/sales_data.py','SalesProjectDataBridge',parent,{'import_module':importer})
    o=with_fixtures(bridge)(self.u);o._fields={'absar_portal_creator_id':NS(type='many2one',comodel_name='res.users')};o.absar_portal_creator_id=self.u
    o._pbw_confirm_own_quotation();self.assertEqual(o.state,'sale');self.assertEqual(o.legacy_closed,1)

class ControllerTests(unittest.TestCase):
 def setUp(self):self.user=User(40,('user',));self.owner=User(41);USERS.update({40:self.user,41:self.owner})
 def test_editing_requires_prepare_not_monitor(self):
  request=NS(env=NS(user=self.user));fn=direct_method(ROOT/'controllers/sales/portal_sales.py','PortalSales','_editable',{'request':request,'Forbidden':Forbidden})
  def denied():raise Forbidden()
  obj=NS(_allowed=denied);o=Order(self.user)
  with self.assertRaises(Forbidden):fn(obj,o)
 def test_all_documents_may_edit_without_becoming_owner(self):
  request=NS(env=NS(user=self.user));fn=direct_method(ROOT/'controllers/sales/portal_sales.py','PortalSales','_editable',{'request':request,'Forbidden':Forbidden})
  o=Order(self.user,owner=self.owner);obj=NS(_allowed=lambda:self.user,_operator=lambda:True)
  fn(obj,o);self.assertEqual(o._pbw_sales_owner(),self.owner)
 def test_full_save_api_enrolls_original_creator_not_editor(self):
  o=Order(self.user,owner=self.owner,prepared=False);req=NS(env=o.env,httprequest=NS(content_length=100))
  req.make_json_response=lambda data,**kw:data
  fn=direct_method(ROOT/'controllers/sales/sales_lines.py','SalesLinesMixin','_line_api',{'request':req,'json':json,'Forbidden':Forbidden,'NotFound':NotFound,'Command':NS(delete=lambda rid:(2,rid))})
  obj=NS(_order=lambda ident:o,_editable=lambda rec:None,_line_version=lambda rec:'v1',_line_boot=lambda rec:{'owner':rec.pbw_portal_creator_id.id})
  result=fn(obj,10,'save',{'payload':json.dumps({'version':'v1','lines':[]})})
  self.assertTrue(result['ok'],result);self.assertEqual(result['result']['owner'],self.owner.id)
  self.assertFalse(o._pbw_review_permissions(self.user)['can_submit'])
 def test_stale_save_does_not_change_ownership(self):
  o=Order(self.user,owner=self.owner,prepared=False);req=NS(env=o.env,httprequest=NS(content_length=100));req.make_json_response=lambda data,**kw:data
  fn=direct_method(ROOT/'controllers/sales/sales_lines.py','SalesLinesMixin','_line_api',{'request':req,'json':json,'Forbidden':Forbidden,'NotFound':NotFound})
  obj=NS(_order=lambda ident:o,_editable=lambda rec:None,_line_version=lambda rec:'v2')
  result=fn(obj,10,'save',{'payload':json.dumps({'version':'v1','lines':[]})})
  self.assertFalse(result['ok']);self.assertFalse(o.pbw_portal_creator_id)
 def test_all_partner_selection_paths_share_one_domain(self):
  s=(ROOT/'controllers/sales/portal_sales.py').read_text()
  self.assertEqual(s.count('_pbw_sales_customer_domain(request.env.user.company_id)'),2)
  self.assertIn('partner not in self._partners(limit=None)',s)
 def test_project_templates_use_resolver_not_empty_local_field(self):
  s=(ROOT/'views/sales/portal_sales_templates.xml').read_text()
  self.assertNotIn('.pbw_project_id',s);self.assertEqual(s.count('._pbw_sales_project()'),3)
 def test_search_domain_uses_project_mapping_hook(self):
  self.assertIn('_pbw_sales_project_search_domain(query)',(ROOT/'controllers/sales/portal_sales.py').read_text())
 def test_direct_button_has_csrf_and_authorization_flag(self):
  from lxml import etree
  doc=etree.parse(str(ROOT/'views/sales/portal_sales_templates.xml'))
  forms=doc.xpath('//form[@t-if="can_confirm_direct"]');self.assertEqual(len(forms),1)
  self.assertTrue(forms[0].xpath('.//input[@name="csrf_token"]'))
  self.assertTrue(forms[0].xpath('.//input[@name="action" and @value="confirm_direct"]'))
 def test_unmodified_non_sales_workspaces_and_notification_assets(self):
  expected=json.loads(Path(__file__).with_name('preserved_v094_hashes.json').read_text())
  for name,digest in expected.items():
   self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
 def test_no_new_custom_dependency_in_base(self):
  m=ast.literal_eval((ROOT/'__manifest__.py').read_text());old=json.loads(Path(__file__).with_name('v094_dependencies.json').read_text());self.assertEqual(m['depends'],old)
 def test_bridge_does_not_install_other_custom_addons(self):
  self.assertEqual(ast.literal_eval((BRIDGE/'__manifest__.py').read_text())['depends'],['portal_backend_workspace', 'employee_portal_suite'])

if __name__=='__main__':unittest.main(verbosity=2)
