"""Offline regression checks against actual source; no running Odoo registry."""
import ast, sys, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
sys.argv=sys.argv[:1]
def method(path, cls, name, ns=None):
 tree=ast.parse((ROOT/path).read_text())
 cl=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
 fn=next(n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name==name)
 fn.decorator_list=[]
 space={'_':lambda s,*a,**kw:s};space.update(ns or {})
 exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),space)
 return space[name]
class User:
 def __init__(self,groups):self.groups={'portal_backend_workspace.'+g for g in groups}
 def ensure_one(self):pass
 def has_group(self,g):return g in self.groups
 def _pbw_has_access(self):return True
class Tests(unittest.TestCase):
 def test_accounting_all_six_dialog_roots_match_source_styles(self):
  s=(ROOT/'static/src/accounting/accounting.js').read_text()
  self.assertNotIn('aca pbw-accounting-dialog',s)
  self.assertEqual(s.count('pbw-accounting pbw-accounting-dialog'),6)
 def test_source_payslip_totals_preserved_conditionally(self):
  s=(ROOT/'controllers/hr/portal.py').read_text()
  self.assertIn("'x_studio_reimbursement'",s)
  self.assertIn("if name in r._fields and r._fields[name].type in ('float', 'monetary', 'integer')",s)
 def test_native_posting_warning_accepts_invoices(self):
  tree=ast.parse((ROOT/'models/accounting/post_confirmation.py').read_text())
  cl=next(n for n in tree.body if isinstance(n,ast.ClassDef))
  field=next(n for n in cl.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='kind')
  self.assertEqual({v[0] for v in ast.literal_eval(field.value.args[0])},{'invoices','bills','refunds','journals'})
 def test_pending_attention_survives_seen_marker(self):
  fn=method('models/workspace.py','WorkspaceUser','_pbw_attention_items')
  summary={k:{'count':3,'new':0,'url':'/my/workspace','label':k} for k in ('sales_approval','purchase_approval','accounting_approval','sales_review_update')}
  result=fn(User([]),summary)
  self.assertEqual([x['key'] for x in result],['sales_approval','purchase_approval','accounting_approval'])
  self.assertEqual(sum(x['count'] for x in result),9)
 def test_new_decisions_only_not_all_historical_decisions(self):
  fn=method('models/workspace.py','WorkspaceUser','_pbw_attention_items')
  result=fn(User([]),{'sales_review_update':{'count':20,'new':2,'label':'Review updates','url':'/my/workspace/sales/updates'}})
  self.assertEqual(result[0]['count'],2)
 def test_badges_pending_not_unread(self):
  fn=method('models/workspace.py','WorkspaceUser','_pbw_navigation_badge')
  self.assertEqual(fn(User([]),{'purchase_approval':{'count':4,'new':0}},'/my/workspace/purchase/approvals'),4)
  self.assertEqual(fn(User([]),{'sales_review_update':{'count':20,'new':2}},'/my/workspace/sales/updates'),2)
 def area_links(self,groups):
  tree=ast.parse((ROOT/'models/workspace.py').read_text())
  names={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id in ('PREFIX','AREAS')}
  fn=method('models/workspace.py','WorkspaceUser','_pbw_workspace_areas',names)
  return {x[1] for a in fn(User(groups)) for x in a['links']}
 def test_combined_sales_roles_show_both_views(self):
  links=self.area_links(['sales__group_portal_sales_creator','sales__group_portal_sales_monitor'])
  self.assertIn('/my/workspace/sales',links);self.assertIn('/my/workspace/sales/monitor',links)
  self.assertNotIn('/my/workspace/sales/approvals',links)
 def test_monitor_does_not_gain_creation_or_approval(self):
  links=self.area_links(['sales__group_portal_sales_monitor'])
  self.assertEqual(links,{'/my/workspace/sales/monitor'})
 def test_purchase_header_preserves_native_role_visibility(self):
  root=etree.parse(str(ROOT/'views/purchase/portal_workspace_pages.xml'))
  cond=root.xpath("//template[@id='purchase__purchase_workspace_nav']/header/@t-if")[0]
  for group,expected in [('purchase__group_portal_purchase_preparer',True),('purchase__group_portal_purchase_approver',False)]:
   self.assertEqual(eval(cond, {'request':NS(env=NS(user=User([group])))}), expected)
 def test_vendor_credit_note_navigation(self):
  self.assertIn('/my/workspace/accounting/refunds',self.area_links(['accounting__group_monitor']))
 def test_hr_employee_role_does_not_gain_payroll(self):
  links=self.area_links(['hr__group_employee_admin'])
  self.assertIn('/my/workspace/hr/employees',links)
  self.assertNotIn('/my/workspace/hr/payslips',links)
 def test_mobile_quick_actions_follow_roles(self):
  root=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  quick=root.xpath("//div[@id='pbwFabMenu']/a")
  def links(groups):
   return {a.get('href') for a in quick if eval(a.get('t-if'),{'request':NS(env=NS(user=User(groups)))})}
  employee=links(['hr__group_employee_admin'])
  self.assertIn('/my/workspace/hr/attendance/new',employee)
  self.assertNotIn('/my/workspace/hr/payslips/new',employee)
  self.assertIn('/my/workspace/accounting/invoices/new',links(['accounting__group_customer_invoicing']))
  self.assertNotIn('/my/workspace/accounting/journals/new',links(['accounting__group_customer_invoicing']))
 def test_explicit_customer_checkbox_matches_original(self):
  s=(ROOT/'controllers/sales/portal_sales.py').read_text()
  self.assertNotIn("('customer_rank','>',0)",s)
  self.assertIn('_pbw_sales_customer_domain(request.env.user.company_ids)',s)
  p=(ROOT/'models/sales/res_partner.py').read_text()
  self.assertIn("[('pbw_is_sales_customer', '=', True)]",p)
 def test_hr_clear_text_matches_original(self):
  fn=method('models/hr/gateway.py','EmployeeAdminGateway','_value')
  self.assertIs(fn(NS(),None,NS(type='char'),''),False)
  self.assertEqual(fn(NS(),None,NS(type='char'),'Name'),'Name')
 def test_hr_period_filter_not_string_membership(self):
  self.assertNotIn("kind in ('payslips')",(ROOT/'models/hr/gateway.py').read_text())
 def test_native_dependency_list_has_no_custom_addon(self):
  m=ast.literal_eval((ROOT/'__manifest__.py').read_text())
  native={'base','web','portal','mail','sale_management','sale_stock','purchase_stock','project_purchase','account','analytic','hr','hr_attendance','hr_contract','hr_work_entry','hr_payroll'}
  self.assertTrue(set(m['depends'])<=native)
 def test_data_and_asset_paths_exist(self):
  m=ast.literal_eval((ROOT/'__manifest__.py').read_text())
  for name in m['data']:self.assertTrue((ROOT/name).is_file(),name)
  for names in m['assets'].values():
   for name in names:self.assertTrue((ROOT/Path(name).relative_to('portal_backend_workspace')).is_file(),name)
 def test_all_xml_and_python_parse(self):
  for p in ROOT.rglob('*.xml'):etree.parse(str(p))
  for p in ROOT.rglob('*.py'):ast.parse(p.read_text())
 def test_no_direct_eps_or_other_custom_import(self):
  for p in list(ROOT.rglob('*.py'))+list(ROOT.rglob('*.xml')):
   if 'validation' in p.parts:continue
   s=p.read_text()
   for token in ('odoo.addons.employee_portal_suite','odoo.addons.absar_','ref="employee_portal_suite.','ref="customer_vendor_portal.','ref="internal_transfer_voucher.'):
    self.assertNotIn(token,s,str(p))
 def test_attention_uses_scoped_source_component(self):
  text=(ROOT/'static/src/core/workspace_layout.css').read_text()
  self.assertIn('.pbw-needs-attention{background:#fff;border:1px solid #e6e8f0;border-radius:22px',text)
  dom=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  self.assertTrue(dom.xpath("//section[@class='pbw-needs-attention mb-4']"))
 def test_actual_native_posting_wizard_branches(self):
  class UserError(Exception):pass
  fn=method('models/accounting/service.py','PortalAccountingService','_act',{'UserError':UserError,'AccessError':UserError,'ValidationError':UserError,'_REVIEW_TOKEN':object()})
  for action_result,allowed in [(None,True),({'type':'ir.actions.act_window','res_model':'account.autopost.bills.wizard'},True),({'type':'ir.actions.act_window','res_model':'some.other.wizard'},False)]:
   rec=NS(state='draft',pbw_accounting_review_required=False,abnormal_amount_warning='',abnormal_date_warning='',ref='',id=5)
   rec._pbw_accounting_lock=lambda v:None
   rec.write=lambda vals:None
   def post(result=action_result):rec.state='posted';return result
   rec.with_context=lambda **kw:NS(action_post=post)
   service=NS(_actor=lambda **kw:(NS(id=8),{'direct':True}),_record=lambda *a:rec,_audit=lambda *a:None,_detail=lambda *a:{'state':rec.state})
   if allowed:self.assertEqual(fn(service,NS(), 'bills',5,'post',{})['state'],'posted')
   else:
    with self.assertRaises(UserError):fn(service,NS(),'bills',5,'post',{})

if __name__=='__main__':unittest.main(verbosity=2)
