"""Regression for shipped proposal-total XML, without a live Odoo registry.

The loader-boundary fixture normalizes %% -> %, matching the difference between
v0.9.7 source and the user's rendered-node traceback. This is not an Odoo import.
Expressions are evaluated strictly: no exception-to-placeholder fallback.
"""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from lxml import etree

BRIDGE = Path(__file__).resolve().parents[2]
BASE = Path(os.environ.get('PBW_ADDON_PATH', BRIDGE.parent / 'portal_backend_workspace'))
OLD_EXPR = "'%.2f%%' % sum(order.absar_proposal_payment_ids.mapped('percentage'))"

class Milestones(list):
    def mapped(self, field):
        if field != 'percentage':
            raise AssertionError(field)
        return list(self)

def evaluate(expression, percentages):
    context = {'order': SimpleNamespace(absar_proposal_payment_ids=Milestones(percentages)), 'sum': sum}
    return eval(compile(expression, '<shipped-total-expression>', 'eval'), {'__builtins__': {}}, context)

def total_node(normalize=False):
    text = (BRIDGE / 'views/proposals.xml').read_text()
    if normalize:
        text = text.replace('%%', '%')
    root = etree.fromstring(text.encode())
    nodes = root.xpath("//template[@id='proposal_document_detail']//strong[t[contains(@t-out, 'absar_proposal_payment_ids')]]")
    if len(nodes) != 1:
        raise AssertionError(f'Expected one total; got {len(nodes)}')
    return nodes[0]

def render_total(percentages, normalize=False):
    node = total_node(normalize)
    child = node.find('t')
    return (node.text or '') + str(evaluate(child.get('t-out'), percentages)) + (child.tail or '')

class ProposalTotalRegression(unittest.TestCase):
    def test_old_source_works_before_xml_loading(self):
        self.assertEqual(evaluate(OLD_EXPR, [50, 40, 10]), '100.00%')

    def test_exact_traceback_is_reproduced_after_percent_normalization(self):
        expression = OLD_EXPR.replace('%%', '%')
        self.assertEqual(expression, "'%.2f%' % sum(order.absar_proposal_payment_ids.mapped('percentage'))")
        with self.assertRaisesRegex(ValueError, 'incomplete format'):
            evaluate(expression, [50, 40, 10])

    def test_empty_milestones(self):
        self.assertEqual(render_total([]), '0.00%')

    def test_single_milestone(self):
        self.assertEqual(render_total([35.5]), '35.50%')

    def test_complete_milestones(self):
        self.assertEqual(render_total([50, 40, 10]), '100.00%')

    def test_incomplete_draft_is_displayable(self):
        self.assertEqual(render_total([33.33, 33.33, 33.33]), '99.99%')

    def test_overallocated_total_is_not_hidden_or_changed(self):
        self.assertEqual(render_total([60, 50]), '110.00%')

    def test_after_loader_normalization(self):
        for values in [[], [0], [35.5], [50, 40, 10], [33.33, 33.33, 33.33], [60, 50]]:
            with self.subTest(values=values):
                self.assertEqual(render_total(values, True), render_total(values))

    def test_percent_is_literal_markup_not_format_syntax(self):
        node = total_node()
        self.assertEqual(node.get('t-translation'), 'off')
        self.assertNotIn('%', node.find('t').get('t-out'))
        self.assertEqual(node.find('t').tail, '%')
        self.assertIsNone(node.get('t-out'))

    def test_original_inheritance_target_and_technical_gate_preserved(self):
        root = etree.parse(str(BRIDGE / 'views/proposals.xml'))
        template = root.xpath('//template[@id="proposal_document_detail"]')[0]
        self.assertEqual(template.get('inherit_id'), 'portal_backend_workspace.sales__document_detail_extra')
        self.assertTrue(template.xpath("./xpath/t[@t-if=\"order._pbw_sales_document_type() == 'technical'\"]"))
        base = etree.parse(str(BASE / 'views/sales/portal_sales_templates.xml'))
        self.assertEqual(len(base.xpath('//template[@id="sales__document_detail_extra"]')), 1)

    def test_all_runtime_xml_files_parse_without_remaining_double_percent(self):
        for addon in [BASE, BRIDGE]:
            for path in addon.rglob('*.xml'):
                if 'validation' in path.parts or 'tests' in path.parts:
                    continue
                with self.subTest(path=str(path.relative_to(addon))):
                    root = etree.parse(str(path))
                    for element in root.iter():
                        for attr, value in element.attrib.items():
                            if attr.startswith('t-'):
                                self.assertNotIn('%%', value, str(path))

    def test_bridge_declaration_keeps_same_dependencies(self):
        data = ast.literal_eval((BRIDGE / '__manifest__.py').read_text())
        self.assertEqual(data['version'], '18.0.0.9.8')
        self.assertEqual(data['depends'], ['portal_backend_workspace', 'employee_portal_suite'])
        self.assertIn('views/proposals.xml', data['data'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
