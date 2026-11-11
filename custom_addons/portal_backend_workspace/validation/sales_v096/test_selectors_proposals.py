"""Run actual shipped methods with controlled fixtures, not a live Odoo registry."""
import ast, copy, importlib.util, json, os, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import datetime

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('retained_sales', HERE/'test_previous_sales.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
ROOT=old.ROOT;BRIDGE=old.BRIDGE
class RS(list):
 @property
 def ids(self):return [r.id for r in self]
 def sudo(self,*a):return self
 def sorted(self,key):return RS(sorted(self,key=lambda x:getattr(x,key)))
 def filtered(self,fn):return RS(x for x in self if fn(x))
 def __getitem__(self,i):
  v=super().__getitem__(i);return RS(v) if isinstance(i,slice) else v
 def mapped(self,name):return [getattr(x,name) for x in self]
class Company:
 def __init__(self,id):self.id=id;self.ids=[id];self.name='Company '+str(id)
 def __eq__(self,v):return hasattr(v,'id') and v.id==self.id
 def __iter__(self):return iter([self])
class Registry(dict):
 def __init__(self,user,**tables):super().__init__(tables);self.user=user;self.company=user.company_ids[0]
class Field:
 def __init__(self,type,relation=None,selection=None):self.type=type;self.comodel_name=relation;self.selection=selection
 def _description_selection(self,env):return self.selection
class TemplateTable:
 def __init__(self,rows):self.rows=rows;self.calls=[]
 def sudo(self):return self
 def search(self,domain,limit=None,**kw):
  self.calls.append(domain);found=[r for r in self.rows if old.matches(domain,r)]
  return found[0] if found else False

Core=old.load_class(ROOT/'models/sales/sale_order.py','SaleOrder',old.Native)
Proposal=old.load_class(BRIDGE/'models/proposals.py','SalesProposalBridge',Core)

def proposal_record(installed=True):
 c1=Company(1);c2=Company(2);u=old.User(60,('approver',));u.company_ids=RS([c1]);u.company_id=c1
 o=Proposal(u);o.company_id=c1;o._fields={};o.env=Registry(u)
 o.absar_proposal_type='standard';o.absar_proposal_title='Original title'
 o.absar_proposal_section_ids=RS();o.absar_proposal_payment_ids=RS();o.absar_proposal_template_id=False
 o.action_absar_load_proposal_template=lambda:None
 if installed:
  for name,kind,model in [
    ('absar_proposal_type','selection',None),('absar_proposal_title','char',None),
    ('absar_proposal_template_id','many2one','absar.proposal.template'),
    ('absar_proposal_section_ids','one2many','absar.proposal.section'),
    ('absar_proposal_payment_ids','one2many','absar.proposal.payment')]:
   o._fields[name]=Field(kind,model,[('standard','Standard Quotation'),('technical','Technical & Financial Proposal')])
   if model:o.env[model]=NS()
  o.env['absar.proposal.template']=TemplateTable([
   NS(id=10,active=True,company_id=c1),NS(id=11,active=True,company_id=False),
   NS(id=12,active=True,company_id=c2),NS(id=13,active=False,company_id=c1)])
 return o,c1,c2

class CustomerTests(unittest.TestCase):
 def setUp(self):
  self.c1=Company(1);self.c2=Company(2);self.c3=Company(3)
  self.base=old.Partner();self.base._fields={}
  self.bridge=old.BridgePartner();self.bridge._fields={'absar_is_sales_customer':Field('boolean')}
 def contact(self,company=None,pbw=False,original=False,active=True):
  return NS(company_id=company or False,pbw_is_sales_customer=pbw,absar_is_sales_customer=original,active=active,customer_rank=100)
 def test_original_checkbox_second_allowed_company_is_visible(self):
  self.assertTrue(old.matches(self.bridge._pbw_sales_customer_domain(RS([self.c1,self.c2])),self.contact(self.c2,original=True)))
 def test_original_checkbox_shared_customer_is_visible(self):
  self.assertTrue(old.matches(self.bridge._pbw_sales_customer_domain(RS([self.c1])),self.contact(original=True)))
 def test_workspace_checkbox_does_not_require_original_addon(self):
  self.assertTrue(old.matches(self.base._pbw_sales_customer_domain(RS([self.c1])),self.contact(pbw=True)))
 def test_no_flags_does_not_fall_back_to_all_contacts_or_customer_rank(self):
  self.assertFalse(old.matches(self.bridge._pbw_sales_customer_domain(RS([self.c1,self.c2])),self.contact()))
 def test_archived_and_foreign_company_contacts_excluded(self):
  for row in [self.contact(self.c1,original=True,active=False),self.contact(self.c3,original=True)]:
   self.assertFalse(old.matches(self.bridge._pbw_sales_customer_domain(RS([self.c1,self.c2])),row))
 def test_provider_status_shows_installed_original_field(self):
  self.assertIn('Customer / Client (original Sales)',self.bridge._pbw_sales_customer_source_labels())
 def test_missing_original_field_status_is_explicit(self):
  self.bridge._fields={};self.assertEqual(self.bridge._pbw_sales_customer_source_labels(),['Workspace Customer / Client'])
 def sales_company(self,partner=False,active=None):
  req=NS(env=NS(user=NS(company_ids=RS([self.c1,self.c2]),company_id=self.c1),company=active or self.c2))
  fn=old.direct_method(ROOT/'controllers/sales/portal_sales.py','PortalSales','_sales_company',{'request':req,'Forbidden':old.Forbidden})
  return fn(NS(),partner)
 def test_shared_customer_uses_active_not_default_company(self):self.assertEqual(self.sales_company(self.contact()),self.c2)
 def test_company_specific_customer_uses_its_authorized_company(self):self.assertEqual(self.sales_company(self.contact(self.c1)),self.c1)
 def test_unassigned_website_company_falls_back_to_authorized_user_company(self):
  self.assertEqual(self.sales_company(self.contact(),active=self.c3),self.c1)
 def test_foreign_company_in_creation_denied(self):
  with self.assertRaises(old.Forbidden):self.sales_company(self.contact(self.c3))
 def test_initial_and_search_more_use_same_allowed_companies(self):
  src=(ROOT/'controllers/sales/portal_sales.py').read_text()
  self.assertEqual(src.count('_pbw_sales_customer_domain(request.env.user.company_ids)'),2)
  self.assertNotIn('_pbw_sales_customer_domain(request.env.user.company_id)',src)

class ProposalTests(unittest.TestCase):
 def test_no_engine_standard_only_and_no_field_access(self):
  o,c1,c2=proposal_record(False);self.assertFalse(o._pbw_has_technical_proposals())
  self.assertEqual(o._pbw_sales_document_types(),[('standard','Standard Quotation')])
  self.assertEqual(o._pbw_sales_document_values('standard',company=c1),{})
  with self.assertRaises(old.ValidationError):o._pbw_sales_document_values('technical',company=c1)
 def test_full_installed_engine_exposes_technical(self):
  o,_,_=proposal_record();self.assertTrue(o._pbw_has_technical_proposals());self.assertIn(('technical','Technical & Financial Proposal'),o._pbw_sales_document_types())
 def test_partial_or_wrong_type_engine_not_exposed(self):
  for missing in ('absar_proposal_type','absar_proposal_title','absar_proposal_section_ids'):
   o,_,_=proposal_record();del o._fields[missing];self.assertFalse(o._pbw_has_technical_proposals())
  o,_,_=proposal_record();o._fields['absar_proposal_type'].type='char';self.assertFalse(o._pbw_has_technical_proposals())
 def test_absent_model_not_exposed(self):
  o,_,_=proposal_record();del o.env['absar.proposal.payment'];self.assertFalse(o._pbw_has_technical_proposals())
 def test_missing_selection_value_not_exposed(self):
  o,_,_=proposal_record();o._fields['absar_proposal_type'].selection=[('standard','Standard Quotation')];self.assertFalse(o._pbw_has_technical_proposals())
 def test_technical_kind_saved_to_existing_field(self):
  o,c1,_=proposal_record();self.assertEqual(o._pbw_sales_document_values('technical',company=c1)['absar_proposal_type'],'technical')
 def test_standard_kind_saved_without_faking_proposal(self):
  o,c1,_=proposal_record();self.assertEqual(o._pbw_sales_document_values('standard',company=c1),{'absar_proposal_type':'standard'})
 def test_invalid_kind_rejected(self):
  o,c1,_=proposal_record()
  with self.assertRaises(old.ValidationError):o._pbw_sales_document_values('arbitrary',company=c1)
 def test_template_same_company_and_shared_allowed(self):
  o,c1,_=proposal_record()
  for ident in (10,11):self.assertEqual(o._pbw_sales_document_values('technical',{'template_id':ident},c1)['absar_proposal_template_id'],ident)
 def test_cross_company_archived_forged_templates_rejected(self):
  o,c1,c2=proposal_record()
  for ident in (12,13,999,True,-1,'x'):
   with self.subTest(ident=ident):
    with self.assertRaises(old.ValidationError):o._pbw_sales_document_values('technical',{'template_id':ident},c1)
  with self.assertRaises(old.ValidationError):o._pbw_proposal_template(12,c2)
  with self.assertRaises(old.ValidationError):o._pbw_proposal_template(0,c1)
  self.assertNotIn('absar_proposal_template_id',o._pbw_sales_document_values('technical',{'template_id':0},c1))
 def test_standard_cannot_apply_template(self):
  o,c1,_=proposal_record()
  with self.assertRaises(old.ValidationError):o._pbw_sales_document_values('standard',{'template_id':10},c1)
 def test_saved_type_label_reads_existing_record(self):
  o,_,_=proposal_record();o.absar_proposal_type='technical';self.assertEqual(o._pbw_sales_document_label(),'Technical & Financial Proposal')
 def test_title_roundtrip_and_length(self):
  o,_,_=proposal_record();o.absar_proposal_type='technical'
  self.assertEqual(o._pbw_sales_document_header_values({'title':'New title'}),{'absar_proposal_title':'New title'})
  self.assertEqual(len(o._pbw_sales_document_header_values({'title':'x'*500})['absar_proposal_title']),160)
  self.assertEqual(o._pbw_sales_document_header_values({}),{})
 def test_proposal_child_changes_invalidate_version(self):
  o,_,_=proposal_record();v1=o._pbw_sales_document_version();o.absar_proposal_section_ids=RS([NS(id=10,write_date='2026-11-08')]);v2=o._pbw_sales_document_version()
  self.assertNotEqual(v1,v2)
 def test_proposal_child_commands_are_in_review_invalidation_fields(self):
  o,_,_=proposal_record();self.assertTrue({'absar_proposal_section_ids','absar_proposal_payment_ids','absar_proposal_type'}.issubset(o._pbw_sales_extra_content_fields()))
 def test_template_loaded_after_real_order_creation(self):
  o,c1,_=proposal_record();o.absar_proposal_type='technical';o.absar_proposal_template_id=NS(id=10);calls=[];o.action_absar_load_proposal_template=lambda:calls.append('load')
  o._pbw_sales_after_document_create();self.assertEqual(calls,['load'])

class RoutesAndTemplates(unittest.TestCase):
 def controller_method(self,name,namespace=None):
  return old.direct_method(BRIDGE/'controllers/proposals.py','WorkspaceSalesProposals',name,{'Forbidden':old.Forbidden,'NotFound':old.NotFound,**(namespace or {})})
 def test_missing_engine_route_blocked(self):
  o,_,_=proposal_record(False);fn=self.controller_method('_proposal_order');obj=NS(_order=lambda _:o)
  with self.assertRaises(old.NotFound):fn(obj,10)
 def test_write_requires_permission_before_and_after_lock(self):
  o,_,_=proposal_record();o.absar_proposal_type='technical';events=[];object.__setattr__(o,'_pbw_portal_lock',lambda:events.append('lock'))
  fn=self.controller_method('_proposal_order',{'request':NS(httprequest=NS(content_length=50))})
  obj=NS(_order=lambda _:o,_editable=lambda _:events.append('authorized'))
  self.assertIs(fn(obj,10,True),o);self.assertEqual(events,['authorized','lock','authorized'])
 def test_no_permission_cannot_lock_or_modify(self):
  o,_,_=proposal_record();o.absar_proposal_type='technical';events=[];object.__setattr__(o,'_pbw_portal_lock',lambda:events.append('lock'))
  def deny(_):raise old.Forbidden()
  with self.assertRaises(old.Forbidden):self.controller_method('_proposal_order')(NS(_order=lambda _:o,_editable=deny),10,True)
  self.assertFalse(events)
 def test_section_save_cannot_target_other_order_child(self):
  o,_,_=proposal_record();o.absar_proposal_section_ids=RS([NS(id=4)])
  with self.assertRaises(old.NotFound):self.controller_method('save_section')(NS(_proposal_order=lambda *a,**k:o),10,999,name='Title')
 def test_reorder_rejects_foreign_and_duplicate_ids(self):
  o,_,_=proposal_record();o.absar_proposal_section_ids=RS([NS(id=4),NS(id=5)])
  fn=self.controller_method('reorder_sections');obj=NS(_proposal_order=lambda *a,**k:o)
  for ids in ('4,4','4,999','4','nope'):
   with self.subTest(ids=ids):
    with self.assertRaises(old.Forbidden):fn(obj,10,section_ids=ids)
 def test_inherited_views_target_existing_stable_slots(self):
  from lxml import etree as E
  base=E.parse(str(ROOT/'views/sales/portal_sales_templates.xml'));bridge=E.parse(str(BRIDGE/'views/proposals.xml'))
  for node in bridge.xpath('//template[@inherit_id]'):
   ident=node.get('inherit_id').split('.',1)[1];self.assertEqual(len(base.xpath('//template[@id=$id]',id=ident)),1)
  self.assertEqual(len(base.xpath('//select[@name="kind"]/option[@t-foreach="document_types"]')),1)
  self.assertEqual(len(base.xpath('//*[@t-out="order._pbw_sales_document_label()"]')),1)
 def test_original_proposal_section_controls_preserved(self):
  from lxml import etree as E
  xml=E.parse(str(BRIDGE/'views/proposals.xml'))
  for name in ('section_type','name','content','include','page_break','position','percentage','due_condition','template_id','title'):
   self.assertTrue(xml.xpath('//*[@name=$name]',name=name),name)
  self.assertTrue(xml.xpath('//*[@data-pbw-sales-format]'))
 def test_all_mutating_routes_auth_user_post_csrf_and_order_guard(self):
  tree=ast.parse((BRIDGE/'controllers/proposals.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
  for fn in cls.body:
   if not isinstance(fn,ast.FunctionDef):continue
   for dec in fn.decorator_list:
    if not isinstance(dec,ast.Call) or not dec.args:continue
    kw={k.arg:ast.literal_eval(k.value) for k in dec.keywords}
    self.assertEqual(kw['auth'],'user');self.assertEqual(kw['methods'],['POST']);self.assertIs(kw['csrf'],True)
    self.assertIn('_proposal_order',ast.unparse(fn),fn.name)
 def test_no_new_custom_dependencies(self):
  manifest=ast.literal_eval((BRIDGE/'__manifest__.py').read_text())
  self.assertEqual(manifest['depends'],['portal_backend_workspace','employee_portal_suite'])
  self.assertNotIn('absar_technical_proposal',ast.literal_eval((ROOT/'__manifest__.py').read_text())['depends'])

if __name__=='__main__':unittest.main(verbosity=2)
