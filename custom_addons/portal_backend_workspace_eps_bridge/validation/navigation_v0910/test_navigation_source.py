"""Source/inheritance/preservation tests; no Odoo runtime is mocked as live."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from zipfile import ZipFile
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'portal_backend_workspace'
BRIDGE=ROOT/'portal_backend_workspace_eps_bridge'
MZIP=Path('/mnt/data/Portal_Backend_Workspace_v0.9.7_Customer_Proposal_Fix.zip')
BZIP=Path('/mnt/data/Portal_Backend_Workspace_EPS_Bridge_v0.9.9_Remove_Signatories.zip')

def tree(p):return E.parse(str(p))
def norm(n):return E.tostring(n,method='c14n')
def runtime(rel):
 parts=Path(rel).parts
 return (parts[0] in ('models','controllers','security','views','static','data','migrations','wizard','wizards')
         or rel in ('__manifest__.py','__init__.py','hooks.py'))

def changes(module,archive):
 out=[]
 with ZipFile(archive) as z:
  old={n.split('/',1)[1]:z.read(n) for n in z.namelist() if not n.endswith('/')}
 for rel,b in old.items():
  if runtime(rel):
   p=module/rel
   if not p.is_file():out.append(('deleted',rel))
   elif b!=p.read_bytes():out.append(('changed',rel))
 for p in module.rglob('*'):
  if p.is_file():
   rel=p.relative_to(module).as_posix()
   if rel not in old and runtime(rel):out.append(('added',rel))
 return sorted(out)

class NavigationTests(unittest.TestCase):
 def test_same_addons_and_dependencies(self):
  for module,zp in ((MAIN,MZIP),(BRIDGE,BZIP)):
   manifest=ast.literal_eval((module/'__manifest__.py').read_text())
   with ZipFile(zp) as z:old=ast.literal_eval(z.read(module.name+'/__manifest__.py').decode())
   self.assertEqual(manifest['version'],'18.0.0.9.10')
   self.assertEqual(manifest['depends'],old['depends'])
   self.assertEqual(manifest['data'],old['data'])
   self.assertEqual(manifest.get('assets'),old.get('assets'))
 def test_only_scoped_runtime_changes(self):
  self.assertEqual(changes(MAIN,MZIP),sorted([('changed','__manifest__.py'),('changed','views/workspace_layout.xml'),('added','static/src/core/workspace_navigation.css')]))
  self.assertEqual(changes(BRIDGE,BZIP),sorted([('changed','__manifest__.py'),('changed','views/navigation.xml')]))
 def test_bell_template_unchanged(self):
  with ZipFile(MZIP) as z:old=E.fromstring(z.read(MAIN.name+'/views/workspace_layout.xml'))
  cur=tree(MAIN/'views/workspace_layout.xml')
  self.assertEqual(norm(old.xpath('//template[@id="notification_bell"]')[0]),norm(cur.xpath('//template[@id="notification_bell"]')[0]))
 def test_history_stays_accessible_from_bell(self):
  doc=tree(MAIN/'views/workspace_layout.xml')
  self.assertEqual(len(doc.xpath('//template[@id="notification_list"]')),1)
  self.assertEqual(len(doc.xpath('//template[@id="notification_bell"]//a[@data-pbw-history]')),1)
  self.assertEqual(doc.xpath('//template[@id="notification_list"]//h2/text()'),['Notification history'])
 def test_notification_link_removed_only_from_sidebar(self):
  doc=tree(MAIN/'views/workspace_layout.xml')
  self.assertFalse(doc.xpath('//nav[@id="pbwep-desktop-sidebar-nav"]//a[@href="/my/workspace/notifications"]'))
  self.assertIn("/my/workspace/notifications",(MAIN/'controllers/workspace.py').read_text())
 def test_switch_is_outside_operation_nav(self):
  doc=tree(MAIN/'views/workspace_layout.xml')
  self.assertFalse(doc.xpath('//nav[@id="pbwep-desktop-sidebar-nav"]//*[@t-foreach="pbw_extra_links"]'))
  self.assertEqual(len(doc.xpath('//aside[@id="pbwep-shared-sidebar"]/t[@t-foreach="pbw_extra_links"]')),1)
 def test_switch_inherits_existing_authorization(self):
  s=(MAIN/'views/workspace_layout.xml').read_text()
  self.assertIn('request.env.user._pbw_extra_navigation()',s)
  doc=tree(BRIDGE/'views/navigation.xml')
  self.assertEqual(doc.xpath('//t[@t-call="portal_backend_workspace.portal_switcher"]/@t-if'),['request.env.user._pbw_has_access()'])
 def test_bridge_same_view_id(self):
  doc=tree(BRIDGE/'views/navigation.xml')
  self.assertEqual(doc.xpath('//template/@id'),['employee_workspace_navigation'])
  self.assertFalse(doc.xpath('//*[@id="pbw-eps-business-workspaces"]'))
 def test_bridge_xpaths_match_original_eps(self):
  doc=tree(ROOT/'reference/employee_portal_layout.xml')
  for xp in tree(BRIDGE/'views/navigation.xml').xpath('//xpath'):
   self.assertEqual(len(doc.xpath(xp.get('expr'))),1)
 def test_applied_bridge_puts_switch_before_eps_menu(self):
  doc=tree(ROOT/'reference/employee_portal_layout.xml')
  xp=tree(BRIDGE/'views/navigation.xml').xpath('//xpath[@position="before"]')[0]
  target=doc.xpath(xp.get('expr'))[0]
  for child in xp:target.addprevious(deepcopy(child))
  self.assertEqual(target.getprevious().get('t-call'),'portal_backend_workspace.portal_switcher')
  self.assertEqual(target.getparent().get('id'),'ep-shared-sidebar')
 def test_home_uses_accounting_card_classes(self):
  doc=tree(MAIN/'views/workspace_layout.xml')
  cards=doc.xpath('//template[@id="workspace_home"]//a[@class="pbw-accounting-card"]')
  self.assertEqual(len(cards),1)
  self.assertEqual(cards[0].get('t-foreach'),'workspace_areas')
  self.assertEqual(cards[0].get('t-att-href'),"area['url']")
  self.assertFalse(cards[0].xpath('.//a'))
  for cls in ('pbw-accounting-card-top','pbw-accounting-card-icon','pbw-accounting-card-arrow','pbw-accounting-card-name','pbw-accounting-card-bottom','pbw-accounting-card-open'):
   self.assertEqual(len(cards[0].xpath('.//*[@class=$c]',c=cls)),1)
 def test_accounting_original_css_unchanged(self):
  with ZipFile(MZIP) as z:self.assertEqual((MAIN/'static/src/accounting/accounting.css').read_bytes(),z.read(MAIN.name+'/static/src/accounting/accounting.css'))
 def test_original_home_attention_retained(self):
  with ZipFile(MZIP) as z:old=E.fromstring(z.read(MAIN.name+'/views/workspace_layout.xml'))
  new=tree(MAIN/'views/workspace_layout.xml')
  self.assertEqual(norm(old.xpath('//section[@aria-labelledby="pbw-attention-title"]')[0]),norm(new.xpath('//section[@aria-labelledby="pbw-attention-title"]')[0]))
 def test_all_runtime_xml_parses(self):
  for module in (MAIN,BRIDGE):
   for p in module.rglob('*.xml'):
    if runtime(p.relative_to(module).as_posix()):tree(p)
 def test_all_runtime_python_parses(self):
  for module in (MAIN,BRIDGE):
   for p in module.rglob('*.py'):
    if runtime(p.relative_to(module).as_posix()):ast.parse(p.read_text(),filename=str(p))
 def test_declared_data_and_assets_exist(self):
  for module in (MAIN,BRIDGE):
   manifest=ast.literal_eval((module/'__manifest__.py').read_text())
   for f in manifest['data']:self.assertTrue((module/f).is_file(),f)
   for assets in manifest.get('assets',{}).values():
    for path in assets:self.assertTrue((ROOT/path).is_file(),path)
 def test_static_stylesheet_exists_and_loads_both_sides(self):
  suffix='/portal_backend_workspace/static/src/core/workspace_navigation.css?v=18.0.0.9.10'
  self.assertTrue((MAIN/'static/src/core/workspace_navigation.css').is_file())
  for p in (MAIN/'views/workspace_layout.xml',BRIDGE/'views/navigation.xml'):
   self.assertEqual(len(tree(p).xpath('//link[@href=$h]',h=suffix)),1)
 def test_proposal_regressions_preserved(self):
  p=BRIDGE/'views/proposals.xml'
  self.assertNotIn('signator',p.read_text().lower())
  self.assertIn("'{:.2f}'.format(sum(order.absar_proposal_payment_ids.mapped('percentage')))",p.read_text())
  with ZipFile(BZIP) as z:self.assertEqual(p.read_bytes(),z.read(BRIDGE.name+'/views/proposals.xml'))
 def test_no_new_script_handler_or_access_grants(self):
  doc=tree(MAIN/'views/workspace_layout.xml')
  sw=doc.xpath('//template[@id="portal_switcher"]')[0]
  self.assertFalse(sw.xpath('.//script | .//*[@onclick]'))
  self.assertEqual(len(sw.xpath('.//a[@t-att-href="pbw_switch_url"]')),1)

if __name__=='__main__':
 unittest.main(verbosity=2)
