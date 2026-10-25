"""Report structure/expression checks; not Odoo/wkhtmltopdf rendering."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from lxml import etree
ROOT=Path(__file__).resolve().parents[1]
class Reports(unittest.TestCase):
 def setUp(self):
  self.tree=etree.parse(str(ROOT/'report/account_statement.xml'))
  self.body=self.tree.xpath('//template[@id="asr_statement_document"]')[0]
 def test_all_report_actions_share_body_and_company_per_document(self):
  for filename,template_id in [('account_statement.xml','asr_account_statement'),('customer_statement.xml','asr_customer_statement'),('vendor_statement.xml','asr_vendor_statement')]:
   tree=etree.parse(str(ROOT/'report'/filename));root=tree.xpath('//template[@id="%s"]'%template_id)[0]
   loop=root.xpath('.//t[@t-foreach="docs"]')[0]
   self.assertEqual(loop.xpath('./t[@t-set="o"]')[0].get('t-value'),'doc')
   self.assertEqual(loop.xpath('./t[@t-set="company"]')[0].get('t-value'),'doc.company_id')
   self.assertEqual(len(loop.xpath('./t[@t-call="web.external_layout"]/t[@t-call="account_statement_reports.asr_statement_document"]')),1)
   self.assertEqual(root.xpath('./t')[0].get('t-call'),'web.html_container')
 def test_seven_or_eight_columns_and_no_description(self):
  heads=self.body.xpath('.//table[@class="asr-lines"]/thead/tr/th')
  for kind,count in [('receivable',7),('payable',7),('employee',8)]:
   active=[head for head in heads if not head.get('t-if') or eval(head.get('t-if'),{},dict(statement_kind=kind))]
   self.assertEqual(len(active),count)
   self.assertIn('Reference',[''.join(head.itertext()).strip() for head in active])
   self.assertNotIn('Description',[''.join(head.itertext()).strip() for head in active])
  self.assertEqual(len(self.body.xpath('.//span[@t-out="l.reference or \'\'"]')),1)
 def test_shared_titles(self):
  expr=self.tree.xpath('//template[@id="asr_account_statement"]//t[@t-set="statement_title"]')[0].get('t-value')
  for kind,title in [('receivable','Customer Statement'),('payable','Vendor Statement'),('employee','Employee Statement')]:
   self.assertEqual(eval(expr,{},dict(statement_kind=kind)),title)
 def test_totals_preserve_existing_values(self):
  class Lines(list):
   def mapped(self,key):return [getattr(line,key) for line in self]
  doc=SimpleNamespace(line_ids=Lines([SimpleNamespace(debit=100,credit=0),SimpleNamespace(debit=0,credit=25)]))
  totals=self.body.xpath('.//div[@class="asr-summary"]//span[@t-out]')
  self.assertEqual([eval(node.get('t-out'),{},dict(doc=doc)) for node in totals],[100,25])
  self.assertEqual(len(self.body.xpath('.//div[@class="asr-summary"]//span[@t-field="doc.final_balance"]')),1)
 def test_scoped_style_and_rounded_teal_reference(self):
  css=self.body.find('style').text
  self.assertIn('#177b83',css);self.assertIn('border-radius:12px',css)
  self.assertIn('.asr-print.asr-employee',css)
  for rule in css.split('}'):
   if '{' in rule:
    selectors=rule.split('{')[0].strip().split(',')
    self.assertTrue(all(selector.strip().startswith('.asr-print') for selector in selectors))
  self.assertIn('display:table-header-group',css)
 def test_xml_expressions_and_manifest(self):
  for path in (ROOT/'report').glob('*.xml'):
   tree=etree.parse(str(path))
   for node in tree.iter():
    for name,value in node.attrib.items():
     if name.startswith('t-att-') or name in ('t-value','t-if','t-elif','t-out','t-esc','t-foreach','t-options'):ast.parse(value,mode='eval')
  manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
  for filename in manifest['data']:self.assertTrue((ROOT/filename).is_file())
if __name__=='__main__':unittest.main(verbosity=2)
