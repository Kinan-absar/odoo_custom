"""Static layout/asset regression checks. No Odoo database required."""
import ast,re,unittest
from pathlib import Path
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]
class LayoutContractTests(unittest.TestCase):
 def test_original_full_width_container(self):
  t=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  wraps=t.xpath("//main[contains(@class,'pbwep-portal-main')]/div[@id='wrap']")
  self.assertEqual(len(wraps),1)
  self.assertEqual(set(wraps[0].get('class').split()),{'container','mt-3','mb-5'})
  self.assertFalse(t.xpath("//main//div[contains(@class,'container-fluid')]"))
 def test_scale_is_only_enabled_by_workspace_shell(self):
  head=etree.parse(str(ROOT/'views/workspace_head.xml'))
  self.assertEqual(head.xpath('//style/parent::t/@t-if'),['pbw_portal_compact_desktop'])
  body=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  self.assertEqual(body.xpath("//t[@t-set='pbw_portal_compact_desktop']/@t-value"),['True'])
 def test_original_desktop_and_print_density(self):
  s=(ROOT/'views/workspace_head.xml').read_text()
  self.assertIn('@media screen and (min-width:769px)',s)
  self.assertIn('html{zoom:.8}',s);self.assertIn('@media print{html{zoom:1}}',s)
  self.assertNotIn('992px',s)
 def test_direct_scripts_with_exports_are_module_scripts(self):
  root=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  for node in root.xpath('//script[@src]'):
   src=node.get('src').split('?')[0]
   if src.startswith('/portal_backend_workspace/'):
    code=(ROOT/src.split('/portal_backend_workspace/',1)[1]).read_text()
    if re.search(r'(?m)^export\s',code):self.assertEqual(node.get('type'),'module',src)
 def test_direct_shell_assets_have_release_token(self):
  root=etree.parse(str(ROOT/'views/workspace_layout.xml'))
  for src in root.xpath('//script/@src | //link/@href'):
   if '/static/src/core/' in src:self.assertIn('?v=18.0.0.9.2',src)
 def test_all_local_js_imports_resolve(self):
  for file in (ROOT/'static/src').rglob('*.js'):
   for path in re.findall(r'from\s*[\'"](\.[^\'"]+)[\'"]',file.read_text()):
    target=file.parent/path
    self.assertTrue(target.is_file() or target.with_suffix('.js').is_file(),str(file)+': '+path)
 def test_original_document_type_field_remains(self):
  root=etree.parse(str(ROOT/'views/sales/portal_sales_templates.xml'))
  node=root.xpath("//template[@id='sales__sales_new']//select[@name='kind']")
  self.assertEqual(len(node),1);self.assertEqual(node[0].xpath('./option/@value'),['standard'])
 def test_purchase_list_columns_match_real_cells(self):
  root=etree.parse(str(ROOT/'views/purchase/portal_purchase_approval_list.xml'))
  cols=len(root.xpath("//div[contains(@class,'pbw-list-header')]/span"))
  cells=len(root.xpath("//article[contains(@class,'pbw-record-card')]/div"))
  self.assertEqual(cols,9);self.assertEqual(cols,cells)
 def test_three_shared_grid_styles_remain_identical(self):
  css=[(ROOT/'static/src'/a/'record_cards.css').read_bytes() for a in ['sales','purchase','accounting']]
  self.assertEqual(css[0],css[1]);self.assertEqual(css[1],css[2])
 def test_original_font_family_and_weights(self):
  s=(ROOT/'views/workspace_layout.xml').read_text()
  self.assertIn('DM+Sans:ital,opsz,wght',s);self.assertIn('0,9..40,300',s);self.assertIn('1,9..40,400',s)
if __name__=='__main__':unittest.main(verbosity=2)
