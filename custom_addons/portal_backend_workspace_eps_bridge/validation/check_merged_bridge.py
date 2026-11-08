"""Package preservation and routing fixtures, NOT an Odoo integration test."""
import ast
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlsplit
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent / 'portal_backend_workspace'
EVIDENCE = json.loads((ROOT / 'validation/merge_sources.json').read_text())
MANIFEST = ast.literal_eval((ROOT / '__manifest__.py').read_text())

class PackageTests(unittest.TestCase):
    def test_existing_runtime_preserved(self):
        for name, digest in EVIDENCE['unchanged_eps_runtime_files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest)

    def test_original_sales_adapter_preserved(self):
        self.assertEqual(hashlib.sha256((ROOT/'models/sales_data.py').read_bytes()).hexdigest(), EVIDENCE['sales_adapter_sha256'])

    def test_only_original_dependencies(self):
        self.assertEqual(MANIFEST['depends'], ['portal_backend_workspace', 'employee_portal_suite'])
        self.assertEqual(MANIFEST['version'], '18.0.0.9.5')
        self.assertIs(MANIFEST['auto_install'], True)

    def test_all_three_model_extensions_imported(self):
        tree = ast.parse((ROOT/'models/__init__.py').read_text())
        imports = [a.name for node in tree.body if isinstance(node, ast.ImportFrom) for a in node.names]
        self.assertEqual(imports, ['users', 'notifications', 'sales_data'])

    def test_no_new_fields_acl_or_migration(self):
        tree = ast.parse((ROOT/'models/sales_data.py').read_text())
        for cl in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            attrs = [t.id for n in cl.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
            self.assertEqual(attrs, ['_inherit'])
        self.assertEqual(MANIFEST['data'], ['views/navigation.xml', 'views/notifications.xml'])
        self.assertFalse((ROOT/'migrations').exists())
        self.assertFalse(any(k.endswith('_hook') for k in MANIFEST))

    def test_new_provider_hooks_exist_in_main_v095(self):
        found = set()
        for p in (BASE/'models').rglob('*.py'):
            tree = ast.parse(p.read_text())
            found.update(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
        for hook in ('_pbw_sales_customer_eligibility_domain', '_pbw_sales_project_field', '_pbw_sales_project',
                     '_pbw_sales_project_values', '_pbw_sales_project_search_domain',
                     '_pbw_native_confirmation_context', '_pbw_after_native_confirmation'):
            self.assertIn(hook, found)

    def test_declared_xml_and_local_assets_exist(self):
        for name in MANIFEST['data']:
            tree = etree.parse(str(ROOT/name))
            for node in tree.xpath('//*[@src]'):
                src = urlsplit(node.attrib['src']).path
                if src.startswith('/portal_backend_workspace_eps_bridge/'):
                    self.assertTrue((ROOT/src.split('/', 2)[2]).is_file(), src)
                elif src.startswith('/portal_backend_workspace/'):
                    self.assertTrue((BASE/src.split('/', 2)[2]).is_file(), src)

    def test_no_separate_bridge_runtime_reference(self):
        for p in ROOT.rglob('*'):
            if p.is_file() and p.suffix in ('.py','.xml','.js') and 'validation' not in p.parts:
                self.assertNotIn('portal_backend_workspace_sales_data_bridge', p.read_text())


# Execute the original controller class bodies with a controlled parent hierarchy.
# This exercises route decisions, not HTTP dispatch or the real Odoo registry.
REQUEST = NS()
class ParentLogin:
    def _login_redirect(self, uid, redirect=None):
        return ('parent', uid, redirect)
class WorkspaceLogin(ParentLogin): pass
class EmployeePortalLogin(ParentLogin): pass
class CustomerPortal:
    @staticmethod
    def home(obj, **kw): return ('native-home', kw)
    @staticmethod
    def account(obj, redirect=None, **kw): return ('native-account', redirect, kw)
class WorkspacePortalHome(CustomerPortal): pass
class EmployeePortalRedirect(CustomerPortal): pass
space = dict(http=NS(route=lambda *a, **k: lambda fn: fn), request=REQUEST,
             WorkspaceLogin=WorkspaceLogin, EmployeePortalLogin=EmployeePortalLogin,
             WorkspacePortalHome=WorkspacePortalHome, EmployeePortalRedirect=EmployeePortalRedirect,
             CustomerPortal=CustomerPortal)
tree = ast.parse((ROOT/'controllers/routing.py').read_text())
classes = ast.Module(body=[n for n in tree.body if isinstance(n, ast.ClassDef)], type_ignores=[])
exec(compile(ast.fix_missing_locations(classes), str(ROOT/'controllers/routing.py'), 'exec'), space)

class RoutingTests(unittest.TestCase):
    def user(self, eps=False, pbw=False, portal=True):
        u = NS(share=portal, _pbw_eps_entry_url=lambda: '/my/employee' if eps else False,
               _pbw_has_access=lambda: pbw)
        table = NS(sudo=lambda: NS(browse=lambda uid: u))
        class Env(dict): pass
        env = Env({'res.users': table}); env.user = u
        REQUEST.env = env
        REQUEST.redirect = lambda url: ('redirect', url)
        return u

    def test_dual_access_login_keeps_eps_destination(self):
        self.user(eps=True, pbw=True)
        self.assertEqual(space['WorkspaceEPSLogin']()._login_redirect(7), '/my/employee')

    def test_workspace_only_login_goes_to_workspace(self):
        self.user(pbw=True)
        self.assertEqual(space['WorkspaceEPSLogin']()._login_redirect(7), '/my/workspace')

    def test_login_keeps_explicit_document_link(self):
        self.user(eps=True, pbw=True)
        for url in ('/my/workspace/sales/123?company_id=1', '/my/employee/approvals'):
            self.assertEqual(space['WorkspaceEPSLogin']()._login_redirect(7, url), ('parent', 7, url))

    def test_internal_user_login_is_unchanged(self):
        self.user(eps=True, pbw=True, portal=False)
        self.assertEqual(space['WorkspaceEPSLogin']()._login_redirect(7), ('parent', 7, None))

    def test_home_routes_dual_access_eps_only_and_workspace_only(self):
        for eps, pbw, target in ((True,True,'/my/employee'), (True,False,'/my/employee'), (False,True,'/my/workspace')):
            self.user(eps=eps, pbw=pbw)
            self.assertEqual(space['WorkspaceEPSHome']().home(), ('redirect', target))

    def test_ordinary_portal_home_and_internal_home_stay_native(self):
        for portal in (True, False):
            self.user(portal=portal)
            self.assertEqual(space['WorkspaceEPSHome']().home(page=1), ('native-home', {'page': 1}))

    def test_profile_route_remains_native(self):
        self.user(eps=True, pbw=True)
        self.assertEqual(space['WorkspaceEPSHome']().account(redirect='/my/workspace'), ('native-account','/my/workspace',{}))

    def test_home_redirect_uses_same_default_policy(self):
        self.user(eps=True, pbw=True)
        self.assertEqual(space['WorkspaceEPSHome']().home_redirect(), ('redirect','/my/employee'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
