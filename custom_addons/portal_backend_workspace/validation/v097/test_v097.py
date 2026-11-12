"""Targeted shipped-method tests under controlled fixtures, not a live registry."""
import ast, copy, importlib.util, json, math, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree as E
import retained_sales as old
R=old.ROOT;B=old.BRIDGE
Command=NS(create=lambda vals:(0,0,vals),update=lambda ident,vals:(1,ident,vals),delete=lambda ident:(2,ident,0))
class RS(list):
 @property
 def id(self):return self[0].id if self else False
 @property
 def ids(self):return [x.id for x in self]
 def sorted(self,key):return RS(sorted(self,key=key if callable(key) else lambda x:getattr(x,key)))
 def mapped(self,key):return [getattr(x,key) for x in self]
 def filtered(self,fn):return RS(x for x in self if fn(x))
class Field:
 def __init__(self,kind,relation=None,selection=None):self.type=kind;self.comodel_name=relation;self.selection=selection
 def _description_selection(self,env):return self.selection
class Env(dict):
 def __init__(self,user):super().__init__();self.user=user
class TemplateTable:
 def __init__(self,rows):self.rows=rows
 def sudo(self):return self
 def search(self,domain,**kw):return next((row for row in self.rows if old.matches(domain,row)),False)
Proposal=old.load_class(B/'models/proposals.py','SalesProposalBridge',old.Core,{'json':json,'math':math,'Command':Command})
TYPES=[('executive','Executive Summary'),('confirmation','Proposal Confirmation & Next Steps'),('custom','Custom Section')]
class Sections:
 _fields={'section_type':Field('selection',selection=TYPES)}
 def sudo(self):return self
 def new(self,vals):
  section=NS(name=False,content='',page_break_before=False,section_type=vals['section_type'])
  def onchange():
   section.name=dict(TYPES)[section.section_type]
   section.content='<p>Original engine confirmation</p>' if section.section_type=='confirmation' else ''
  section._onchange_section_type_name=onchange
  return section

def order(engine=True):
 u=old.User(90,('approver',));o=Proposal(u);o.env=Env(u);o._fields={};o.loads=0
 def load():o.loads+=1
 o.action_absar_load_proposal_template=load
 o.absar_proposal_type='technical';o.absar_proposal_title='Title';o.absar_proposal_template_id=False
 o.absar_proposal_section_ids=RS();o.absar_proposal_payment_ids=RS()
 if engine:
  for name,kind,rel in [('absar_proposal_type','selection',None),('absar_proposal_title','char',None),('absar_proposal_template_id','many2one','absar.proposal.template'),('absar_proposal_section_ids','one2many','absar.proposal.section'),('absar_proposal_payment_ids','one2many','absar.proposal.payment')]:
   o._fields[name]=Field(kind,rel,[('standard','Standard Quotation'),('technical','Technical & Financial Proposal')])
   if rel:o.env[rel]=NS()
  for name in ('reference','signatory','signatory_title','customer_signatory','customer_signatory_title'):
   o._fields['absar_proposal_'+name]=Field('char')
  o.env['absar.proposal.section']=Sections()
  o.env['absar.proposal.template']=TemplateTable([NS(id=10,company_id=u.company_id,active=True),NS(id=11,company_id=old.COMPANY2,active=True),NS(id=12,company_id=u.company_id,active=False)])
 return o

def payload():return {'sections':[{'name':'Scope','section_type':'custom','content':'<p>Saved content</p>','include_in_report':True,'page_break_before':True}], 'payments':[{'name':'Advance','percentage':75,'due_condition':'On order'},{'name':'Handover','percentage':25,'due_condition':'On handover'}]}

class CanonicalCustomer(unittest.TestCase):
 def test_original_field_is_stored_boolean_and_not_a_related_copy(self):
  source=(R/'models/sales/res_partner.py').read_text();tree=ast.parse(source)
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
  field=next(n for n in cls.body if isinstance(n,ast.Assign) and n.targets[0].id=='absar_is_sales_customer')
  self.assertEqual(ast.unparse(field.value.func),'fields.Boolean');self.assertNotIn('related',[x.arg for x in field.value.keywords])
 def test_user_facing_label_and_field_restored(self):
  xml=E.parse(str(R/'views/sales/res_partner_views.xml'))
  nodes=xml.xpath('//field[@id="pbw_sales_customer_flag"]');self.assertEqual(len(nodes),1)
  self.assertEqual(nodes[0].get('name'),'absar_is_sales_customer');self.assertEqual(nodes[0].get('string'),'Customer / Client')
  self.assertFalse(xml.xpath('//field[@name="pbw_is_sales_customer"]'))
 def view(self,markup):
  arch=E.fromstring(markup)
  class Parent:
   def _get_view(self,*a,**kw):return arch,'fixture'
  cls=old.load_class(R/'models/sales/res_partner.py','ResPartner',Parent,{'deepcopy':copy.deepcopy})
  result,ident=cls()._get_view(view_type='form');self.assertEqual(ident,'fixture');return arch,result
 def test_original_widget_wins_without_changing_cached_arch(self):
  original,render=self.view('<form><field name="absar_is_sales_customer"/><field name="absar_is_sales_customer" id="pbw_sales_customer_flag"/></form>')
  self.assertEqual(len(render.xpath('//field')),1);self.assertEqual(len(original.xpath('//field')),2)
 def test_standalone_renders_single_customer_widget(self):
  original,render=self.view('<form><field name="absar_is_sales_customer" id="pbw_sales_customer_flag"/></form>');self.assertIs(original,render)
 def test_hidden_original_field_does_not_hide_only_visible_checkbox(self):
  _,render=self.view('<form><field name="absar_is_sales_customer" invisible="1"/><field name="absar_is_sales_customer" id="pbw_sales_customer_flag"/></form>');self.assertEqual(len(render.xpath('//field')),2)
 def test_single_source_labels(self):self.assertEqual(old.Partner()._pbw_sales_customer_source_labels(),['Customer / Client'])

class Upgrade(unittest.TestCase):
 def migrate(self,columns):
  spec=importlib.util.spec_from_file_location('migration',R/'migrations/18.0.0.9.7/pre-migrate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  class Cursor:
   def __init__(self):self.calls=[]
   def execute(self,sql,*args):self.calls.append(sql)
   def fetchall(self):return [(c,) for c in columns]
  c=Cursor();m.migrate(c,'18.0.0.9.6');return c.calls
 def test_existing_original_true_and_false_are_not_written(self):
  sql=self.migrate({'absar_is_sales_customer','pbw_is_sales_customer'});self.assertEqual(len(sql),1)
 def test_pbw_only_database_recovers_existing_values_once(self):
  sql=self.migrate({'pbw_is_sales_customer'});self.assertEqual(len(sql),3);self.assertIn('ADD COLUMN absar_is_sales_customer',sql[1]);self.assertIn('COALESCE(pbw_is_sales_customer, FALSE)',sql[2])
 def test_no_existing_flags_does_not_select_every_contact(self):
  sql=self.migrate(set());self.assertEqual(len(sql),2);self.assertFalse(any('SET absar_is_sales_customer=TRUE' in s for s in sql))
 def test_migration_reentrant_preserves_canonical(self):self.assertEqual(len(self.migrate({'absar_is_sales_customer'})),1)

class DraftProposals(unittest.TestCase):
 def test_new_content_mapped_to_original_models(self):
  values=order()._pbw_proposal_draft_values(json.dumps(payload()))
  self.assertEqual(values['absar_proposal_section_ids'][0],(0,0,{'name':'Scope','section_type':'custom','content':'<p>Saved content</p>','sequence':10,'include_in_report':True,'page_break_before':True}))
  self.assertEqual([c[2]['sequence'] for c in values['absar_proposal_payment_ids']],[10,20])
 def test_new_kind_title_template_and_content_saved_together(self):
  o=order();values=o._pbw_sales_document_values('technical',{'template_id':'10','title':'New title','reference':'REF-1','proposal_payload':json.dumps(payload())},o.company_id)
  self.assertEqual(values['absar_proposal_type'],'technical');self.assertEqual(values['absar_proposal_reference'],'REF-1');self.assertEqual(values['absar_proposal_template_id'],10)
  self.assertEqual(len(values['absar_proposal_payment_ids']),2)
 def test_empty_custom_proposal_valid(self):self.assertEqual(order()._pbw_proposal_draft_values('{}'),{'absar_proposal_section_ids':[],'absar_proposal_payment_ids':[]})
 def test_missing_engine_standard_only(self):
  o=order(False);self.assertEqual(o._pbw_sales_document_types(),[('standard','Standard Quotation')])
  with self.assertRaises(old.ValidationError):o._pbw_sales_document_values('technical',{},o.company_id)
 def test_existing_original_reference_and_signatory_fields_supported(self):
  o=order();vals=o._pbw_sales_document_header_values({'reference':'A','signatory':'B','signatory_title':'CEO','customer_signatory':'C','customer_signatory_title':'Manager'})
  self.assertEqual(vals['absar_proposal_signatory'],'B');self.assertEqual(len(vals),5)
 def test_unknown_header_does_not_write_arbitrary_field(self):self.assertEqual(order()._pbw_sales_document_header_values({'company_id':55,'state':'sale'}),{})
 def test_header_length_and_type_guard(self):
  o=order();self.assertEqual(len(o._pbw_sales_document_header_values({'reference':'x'*300})['absar_proposal_reference']),160)
  with self.assertRaises(old.ValidationError):o._pbw_sales_document_header_values({'reference':{'bad':'value'}})
 def test_empty_reference_can_be_cleared(self):self.assertIs(order()._pbw_sales_document_header_values({'reference':''})['absar_proposal_reference'],False)
 def test_child_ids_and_unknown_fields_rejected(self):
  for group,key,value in [('sections','id',12),('sections','order_id',99),('payments','id',77),('payments','amount',999)]:
   p=payload();p[group][0][key]=value
   with self.subTest(group=group,key=key),self.assertRaises(old.ValidationError):order()._pbw_proposal_draft_values(json.dumps(p))
 def test_invalid_json_shape_rejected(self):
  for raw in ['null','[]','{','{"fields":{}}','{"sections":{}}','{"payments":1}']:
   with self.subTest(raw=raw),self.assertRaises(old.ValidationError):order()._pbw_proposal_draft_values(raw)
 def test_invalid_section_types_names_and_flags_rejected(self):
  for key,val in [('section_type','bogus'),('name',''),('name',{}),('include_in_report','yes'),('page_break_before',1),('content',False)]:
   p=payload();p['sections'][0][key]=val
   with self.subTest(key=key),self.assertRaises(old.ValidationError):order()._pbw_proposal_draft_values(json.dumps(p))
 def test_invalid_percentages_rejected(self):
  for val in [-1,101,'NaN','Infinity',True,'not number']:
   p=payload();p['payments'][0]['percentage']=val
   with self.subTest(val=val),self.assertRaises(old.ValidationError):order()._pbw_proposal_draft_values(json.dumps(p))
 def test_draft_partial_percentages_permitted_until_native_print_check(self):
  p=payload();p['payments']=p['payments'][:1];self.assertEqual(len(order()._pbw_proposal_draft_values(json.dumps(p))['absar_proposal_payment_ids']),1)
 def test_oversized_payload_and_counts_rejected(self):
  for raw in [' '*1000001,json.dumps({'sections':payload()['sections']*101}),json.dumps({'payments':payload()['payments']*26})]:
   with self.assertRaises(old.ValidationError):order()._pbw_proposal_draft_values(raw)
 def test_tampered_foreign_or_archived_template_rejected(self):
  o=order()
  for value in [11,12,999,True,-1]:
   with self.subTest(template=value),self.assertRaises(old.ValidationError):o._pbw_sales_document_values('technical',{'template_id':value},o.company_id)
 def test_after_create_does_not_overwrite_user_edited_template_content(self):
  o=order();o.absar_proposal_template_id=NS(id=10);o._pbw_sales_after_document_create(header={'proposal_payload':json.dumps(payload())});self.assertEqual(o.loads,0)
 def test_older_create_client_still_loads_native_template(self):
  o=order();o.absar_proposal_template_id=NS(id=10);o._pbw_sales_after_document_create();self.assertEqual(o.loads,1)
 def test_confirmation_defaults_come_from_installed_engine(self):
  o=order();default=o._pbw_proposal_default_section('confirmation');self.assertEqual(default['content'],'<p>Original engine confirmation</p>')
 def test_reference_and_signatories_invalidate_review(self):
  fields=order()._pbw_sales_extra_content_fields();self.assertIn('absar_proposal_reference',fields);self.assertIn('absar_proposal_customer_signatory',fields)

class RoutesAndViews(unittest.TestCase):
 def test_all_routes_require_authenticated_post_csrf(self):
  cls=next(n for n in ast.parse((B/'controllers/proposals.py').read_text()).body if isinstance(n,ast.ClassDef))
  for fn in cls.body:
   if not isinstance(fn,ast.FunctionDef):continue
   for dec in fn.decorator_list:
    if isinstance(dec,ast.Call) and dec.args:
     opts={k.arg:ast.literal_eval(k.value) for k in dec.keywords};self.assertEqual(opts['auth'],'user');self.assertEqual(opts['methods'],['POST']);self.assertIs(opts['csrf'],True)
     if fn.name=='proposal_template_preview':self.assertIn('self._allowed()',ast.unparse(fn));self.assertNotIn('.create(',ast.unparse(fn));self.assertNotIn('.write(',ast.unparse(fn))
     else:self.assertIn('write=True',ast.unparse(fn))
 def test_saved_milestone_foreign_child_rejected(self):
  o=order();o.absar_proposal_payment_ids=RS([NS(id=5)])
  fn=old.direct_method(B/'controllers/proposals.py','WorkspaceSalesProposals','save_milestone',{'Command':Command,'NotFound':old.NotFound})
  with self.assertRaises(old.NotFound):fn(NS(_proposal_order=lambda *a,**k:o),10,99)
 def test_saved_milestone_updates_and_reorders_only_owned_children(self):
  o=order();a=NS(id=5,sequence=10);b=NS(id=6,sequence=20);o.absar_proposal_payment_ids=RS([a,b]);writes=[];object.__setattr__(o,'write',lambda vals:writes.append(vals))
  fn=old.direct_method(B/'controllers/proposals.py','WorkspaceSalesProposals','save_milestone',{'Command':Command,'NotFound':old.NotFound,'BASE':'/my/workspace/sales','request':NS(redirect=lambda url:url)})
  obj=NS(_proposal_order=lambda *a,**k:o,_num=lambda x,field:float(x));url=fn(obj,10,6,name='Balance',percentage='25',due_condition='Handover',position='1')
  self.assertEqual(url,'/my/workspace/sales/10');self.assertEqual(writes[0]['absar_proposal_payment_ids'][0][1],6);self.assertEqual(writes[0]['absar_proposal_payment_ids'][0][2]['sequence'],10)
 def test_new_template_inheritance_targets_real_nodes(self):
  core=E.parse(str(R/'views/sales/portal_sales_templates.xml'));view=E.parse(str(B/'views/proposals.xml'))
  for tpl in view.xpath('//template[@inherit_id]'):
   target=core.xpath('//template[@id=$id]',id=tpl.get('inherit_id').split('.',1)[1]);self.assertEqual(len(target),1)
   for x in tpl.xpath('./xpath'):self.assertTrue(target[0].xpath(x.get('expr')),x.get('expr'))
 def test_proposal_payload_explicitly_new_only(self):
  view=E.parse(str(B/'views/proposals.xml'));self.assertTrue(view.xpath('//textarea[@name="proposal_payload" and @data-pbw-sales-create-only]'))
 def test_original_controls_preserved(self):
  view=E.parse(str(B/'views/proposals.xml'))
  for attr in ['section_type','name','content','position','include','page_break','percentage','due_condition','template_id']:
   self.assertTrue(view.xpath('//*[@name=$name]',name=attr),attr)
 def test_new_scripting_declared_in_bridge_assets(self):
  manifest=ast.literal_eval((B/'__manifest__.py').read_text());self.assertIn('portal_backend_workspace_eps_bridge/static/src/proposal_draft.js',manifest['assets']['web.assets_frontend'])
 def test_only_original_two_addons_required(self):
  self.assertEqual(ast.literal_eval((B/'__manifest__.py').read_text())['depends'],['portal_backend_workspace','employee_portal_suite'])

if __name__=='__main__':unittest.main(verbosity=2)
