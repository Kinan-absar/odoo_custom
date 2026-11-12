"""Targeted template and source checks. Does not start an Odoo registry."""
import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from lxml import etree as E

ADDON = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
XML = ADDON / 'views/proposals.xml'
SIGNATORY_KEYS = {'signatory', 'signatory_title', 'customer_signatory', 'customer_signatory_title'}


def tree():
    return E.parse(str(XML))


def normalized(original):
    doc = E.parse(str(original))
    for el in doc.xpath('//*[@t-foreach]'):
        value = el.get('t-foreach')
        try:
            entries = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(entries, list) and entries and all(isinstance(x, tuple) and len(x) == 2 for x in entries):
            if any(x[0] in SIGNATORY_KEYS for x in entries):
                el.set('t-foreach', repr([x for x in entries if x[0] not in SIGNATORY_KEYS]))
    for details in doc.xpath('//details[summary[text()="Signatories"]]'):
        wrapper = details.getparent()
        wrapper.getparent().remove(wrapper)
    parser = E.XMLParser(remove_blank_text=True)
    return E.tostring(E.fromstring(E.tostring(doc), parser), method='c14n')


class Cleanup(unittest.TestCase):
    def test_no_signatory_labels_or_controls_in_active_template(self):
        self.assertNotIn('signator', XML.read_text().lower())

    def test_saved_editable_header_only_title_reference(self):
        nodes = tree().xpath('//template[@id="proposal_document_header"]//*[@t-foreach]')
        self.assertEqual(len(nodes), 1)
        self.assertEqual(ast.literal_eval(nodes[0].get('t-foreach')), [('title', 'Proposal title'), ('reference', 'External Proposal Reference')])

    def test_saved_readonly_header_only_title_reference(self):
        nodes = tree().xpath('//template[@id="proposal_document_detail"]//div[@t-if="not can_edit"]//*[@t-as="entry"]')
        self.assertEqual(len(nodes), 1)
        self.assertEqual([x[0] for x in ast.literal_eval(nodes[0].get('t-foreach'))], ['title', 'reference'])

    def test_new_form_has_no_signatories_disclosure(self):
        self.assertFalse(tree().xpath('//template[@id="proposal_document_new"]//details'))
        self.assertFalse(tree().xpath('//template[@id="proposal_document_new"]//*[@t-as="entry"]'))

    def test_new_title_reference_template_payload_retained(self):
        names = set(tree().xpath('//template[@id="proposal_document_new"]//*[@name]/@name'))
        self.assertEqual(names, {'title', 'reference', 'template_id', 'proposal_payload'})

    def test_only_signatory_markup_changed(self):
        self.assertEqual(normalized(HERE / 'source_proposals_v098.xml'), normalized(XML))

    def test_ids_and_inheritance_targets_retained(self):
        old = E.parse(str(HERE / 'source_proposals_v098.xml'))
        self.assertEqual([(x.get('id'), x.get('inherit_id')) for x in old.xpath('//template')], [(x.get('id'), x.get('inherit_id')) for x in tree().xpath('//template')])

    def test_other_runtime_byte_identical(self):
        records = json.loads((HERE / 'preservation.json').read_text())
        self.assertEqual({r['path'] for r in records['changed_runtime']}, {'__manifest__.py', 'views/proposals.xml'})
        for record in records['unchanged_runtime']:
            with self.subTest(path=record['path']):
                self.assertEqual(hashlib.sha256((ADDON / record['path']).read_bytes()).hexdigest(), record['before_sha256'])

    def test_manifest_upgrade_same_dependencies(self):
        manifest = ast.literal_eval((ADDON / '__manifest__.py').read_text())
        self.assertEqual(manifest['version'], '18.0.0.9.9')
        self.assertEqual(manifest['depends'], ['portal_backend_workspace', 'employee_portal_suite'])
        self.assertIn('views/proposals.xml', manifest['data'])
        for rel in manifest['data']:
            self.assertTrue((ADDON / rel).is_file(), rel)

    def test_absent_signatory_inputs_do_not_clear_stored_fields(self):
        source = ast.parse((ADDON / 'models/proposals.py').read_text())
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'SalesProposalBridge')
        fn = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_pbw_proposal_header_values'))
        fn.decorator_list = []
        scope = {'ValidationError': ValueError, '_': lambda s: s}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), '<actual-proposal-header-method>', 'exec'), scope)
        provider = SimpleNamespace(_pbw_proposal_header_map=lambda: {'title': 'absar_proposal_title', 'reference': 'absar_proposal_reference', **{key: 'absar_proposal_' + key for key in SIGNATORY_KEYS}})
        result = scope[fn.name](provider, {'title': 'Existing proposal', 'reference': 'REF-01'})
        self.assertEqual(result, {'absar_proposal_title': 'Existing proposal', 'absar_proposal_reference': 'REF-01'})
        self.assertEqual(scope[fn.name](provider, {}), {})

    def test_runtime_python_and_xml_parse(self):
        for prefix in ('models', 'controllers'):
            for path in (ADDON / prefix).glob('*.py'):
                ast.parse(path.read_text(), filename=str(path))
        for path in (ADDON / 'views').glob('*.xml'):
            E.parse(str(path))

    def test_previous_total_fix_is_still_literal_percent(self):
        node = tree().xpath('//strong[t[contains(@t-out, "absar_proposal_payment_ids")]]')[0]
        self.assertEqual(node.get('t-translation'), 'off')
        self.assertNotIn('%', node.find('t').get('t-out'))
        self.assertEqual(node.find('t').tail, '%')


if __name__ == '__main__':
    unittest.main(verbosity=2)
