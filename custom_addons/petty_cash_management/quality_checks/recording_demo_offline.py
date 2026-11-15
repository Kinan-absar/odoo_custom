"""Focused offline checks. Not an Odoo installation/integration test."""
import ast
import io
from pathlib import Path
import unittest
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def load_function(path, name):
    tree = ast.parse(path.read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    node = nodes[0];node.decorator_list = []
    code = compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),str(path),'exec')
    namespace = {};exec(code,namespace);return namespace[name]


class OfflineRecordingChecks(unittest.TestCase):
    def test_sample_pdf_parses_and_preserves_amounts(self):
        make_pdf = load_function(ROOT/'models/recording_demo.py','sample_receipt_pdf')
        data = make_pdf('DEMO-R-1 (test)', ['Before VAT: 180.00 USD','VAT: 27.00','Total: 207.00'])
        pdf = PdfReader(io.BytesIO(data))
        self.assertEqual(len(pdf.pages),1)
        text = pdf.pages[0].extract_text()
        self.assertIn('NOT A VALID TAX INVOICE',text)
        self.assertIn('DEMO-R-1 (test)',text)
        self.assertIn('Total: 207.00',text)

    def test_taxable_and_non_taxable_fixture_lines(self):
        compute = load_function(ROOT/'models/petty_cash_line.py','_compute_amounts')
        class Tax:
            def compute_all(self, amount, **kw):return {'taxes':[{'amount':round(amount*.15,2)}]}
        class Row:pass
        rows = []
        for applicable in [True,False]:
            line = Row();line.vat_applicable = applicable;line.amount_before_vat = 180
            line.currency_id = False;line.category_id = Row();line.category_id.tax_id = Tax();rows.append(line)
        compute(rows)
        self.assertEqual((rows[0].vat_amount,rows[0].amount_total),(27,207))
        self.assertEqual((rows[1].vat_amount,rows[1].amount_total),(0,180))

    def test_module_data_load_order_and_assets(self):
        for module in [ROOT,ROOT.parent/'petty_cash_management_portal_bridge']:
            manifest = ast.literal_eval((module/'__manifest__.py').read_text())
            for name in manifest['data']:self.assertTrue((module/name).is_file(),name)
        source = (ROOT/'__manifest__.py').read_text()
        self.assertLess(source.index("'views/menus.xml'"),source.index("'views/recording_demo_views.xml'"))

    def test_portal_extension_does_not_define_a_user_type(self):
        # No demo-defined groups/users/XML identities: access is additive only.
        from lxml import etree
        bridge = ROOT.parent/'petty_cash_management_portal_bridge/views/recording_demo_views.xml'
        doc = etree.parse(str(bridge))
        self.assertFalse(doc.xpath("//record[@model='res.users' or @model='res.groups']"))
        self.assertTrue(doc.xpath("//field[@name='portal_user_id']"))


if __name__=='__main__':unittest.main(verbosity=2)
