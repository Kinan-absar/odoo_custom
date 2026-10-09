"""Offline checks for packaging and destructive migration guards.

The small ORM double tests action identity and cleanup refusal logic, not Odoo
installation or QWeb rendering. Those require the real target database.
"""
import ast
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'data/report_manifest.json').read_text())
odoo = types.ModuleType('odoo')
odoo.api = types.SimpleNamespace(model=lambda method: method)
odoo.fields = types.SimpleNamespace()
odoo.models = types.SimpleNamespace(AbstractModel=object)
exc = types.ModuleType('odoo.exceptions')
class UserError(Exception):
    pass
exc.UserError = UserError
exc.AccessError = UserError
sys.modules['odoo'] = odoo
sys.modules['odoo.exceptions'] = exc
spec = importlib.util.spec_from_file_location('migration_under_test', ROOT / 'models/report_migration.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class Records:
    def __init__(self, name, rows=()):
        self._name = name
        self.rows = list(rows)

    def __bool__(self):
        return bool(self.rows)

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(Records(self._name, [row]) for row in self.rows)

    def __getattr__(self, key):
        if key == 'ids':
            return [r['id'] for r in self.rows]
        if len(self.rows) != 1:
            raise AttributeError(key)
        return self.rows[0].get(key)

    def __or__(self, other):
        return Records(self._name, {r['id']: r for r in self.rows + other.rows}.values())

    def exists(self):
        return self

    def with_context(self, **kwargs):
        return self

    def browse(self):
        return Records(self._name)

    def filtered(self, field):
        return Records(self._name, [r for r in self.rows if r.get(field)])

    def mapped(self, field):
        return [r.get(field) for r in self.rows]

    def search(self, domain):
        def match(row):
            for field, op, value in domain:
                actual = row.get(field)
                if op == '=' and actual != value:
                    return False
                if op == '!=' and actual == value:
                    return False
                if op == 'in' and actual not in value:
                    return False
                if op == 'not in' and actual in value:
                    return False
            return True
        return Records(self._name, [r for r in self.rows if match(r)])


class Env:
    def __init__(self, views=(), reports=(), refs=None):
        self.tables = {'ir.ui.view': Records('ir.ui.view', views),
                       'ir.actions.report': Records('ir.actions.report', reports),
                       'ir.model.data': Records('ir.model.data')}
        self.refs = refs or {}

    def __getitem__(self, name):
        return self.tables[name]

    def ref(self, name, raise_if_not_found=False):
        return self.refs.get(name, False)


def runner(env):
    obj = migration.AbsarReportMigration()
    obj.env = env
    return obj


class PackageTests(unittest.TestCase):
    def test_all_xml_and_python_parse(self):
        for path in ROOT.rglob('*.py'):
            ast.parse(path.read_text())
        for path in ROOT.rglob('*.xml'):
            tree = etree.fromstring(path.read_bytes())
            for element in tree.iter():
                for name, value in element.attrib.items():
                    if name in ('t-if', 't-elif', 't-value', 't-out', 't-esc', 't-foreach') or name.startswith('t-att-'):
                        ast.parse(value, mode='eval')

    def test_no_staging_ids_and_complete_template_calls(self):
        keys = {v['key'] for v in MANIFEST['views']}
        retired = {v['key'] for v in MANIFEST['retired_views']}
        self.assertFalse(keys & retired)
        calls = set()
        for item in MANIFEST['views']:
            source = (ROOT / item['file']).read_text()
            self.assertNotIn('browse(10282)', source)
            self.assertNotIn('browse(10283)', source)
            self.assertNotIn('1877-f39d5ca2', source)
            self.assertNotIn('dev.odoo.com', source)
            calls.update(etree.fromstring(source.encode()).xpath('//@t-call'))
        self.assertFalse(calls & retired)
        self.assertEqual(calls - keys, {'purchase.report_purchaseorder_document', 'web.address_layout', 'web.external_layout', 'web.html_container'})
        self.assertNotIn('purchase.document_tax_totals_copy_4', retired)
        self.assertNotIn('sale.document_tax_totals_copy_4', retired)
        self.assertNotIn('purchase.document_tax_totals_copy_4_copy_2', retired)
        self.assertEqual(len(retired), 73)

    def test_assets_and_paper(self):
        for name, size in [('letterhead.png', (1920, 329)), ('footer.png', (1920, 106)), ('stamp.png', (288, 307))]:
            with Image.open(ROOT / 'static/img' / name) as img:
                self.assertEqual(img.size, size)
                img.verify()
        source = (ROOT / 'models/report_migration.py').read_text()
        self.assertIn('margin_top=45, margin_bottom=10', source)
        self.assertIn('margin_left=7, margin_right=7, header_spacing=40', source)

    def test_reuse_original_invoice_and_pi_external_ids(self):
        for alias in ('invoice_report', 'invoice_payment_report', 'proforma_report'):
            item = next(r for r in MANIFEST['reports'] if r['alias'] == alias)
            old = Records('ir.actions.report', [{'id': 98, 'model': item['model'], 'name': 'Original old name', 'report_name': 'original.copy'}])
            obj = runner(Env(refs={item['xmlid']: old}))
            self.assertEqual(obj._report(item).id, 98)

    def test_ambiguous_actions_stop(self):
        item = next(r for r in MANIFEST['reports'] if r['alias'] == 'quotation_report')
        reports = [dict(id=i, model=item['model'], name=item['name']) for i in (1, 2)]
        with self.assertRaises(UserError):
            runner(Env(reports=reports))._report(item)

    def test_inactive_duplicate_wrapper_does_not_block_retained_key(self):
        views = [dict(id=1, key='absar.subcontract', active=False, arch_db='<t/>'),
                 dict(id=2, key='absar.subcontract', active=True, arch_db='<t/>'),
                 dict(id=3, key='wrapper', active=True, arch_db='<t t-call="absar.subcontract"/>')]
        env = Env(views=views)
        runner(env)._check_cleanup_references(Records('ir.ui.view', [views[0]]), Records('ir.actions.report'))

    def test_live_template_dependency_stops_cleanup(self):
        views = [dict(id=1, key='old.copy', active=False, arch_db='<t/>'),
                 dict(id=2, key='live', active=True, arch_db='<t t-call="old.copy"/>')]
        with self.assertRaises(UserError):
            runner(Env(views=views))._check_cleanup_references(Records('ir.ui.view', [views[0]]), Records('ir.actions.report'))

    def test_unlisted_inherited_view_stops_cascade_delete(self):
        views = [dict(id=1, key='old.copy', active=False),
                 dict(id=2, key='unlisted', name='Unlisted inherited view', active=False, inherit_id=1)]
        with self.assertRaises(UserError):
            runner(Env(views=views))._check_cleanup_references(Records('ir.ui.view', [views[0]]), Records('ir.actions.report'))

    def test_live_button_stops_action_delete(self):
        views = [dict(id=1, key='form', active=True, arch_db='<form><button type="action" name="54"/></form>')]
        actions = [dict(id=54, report_name='old.copy', name='Old Copy')]
        with self.assertRaises(UserError):
            runner(Env(views=views, reports=actions))._check_cleanup_references(Records('ir.ui.view'), Records('ir.actions.report', actions))


if __name__ == '__main__':
    unittest.main(verbosity=2)
