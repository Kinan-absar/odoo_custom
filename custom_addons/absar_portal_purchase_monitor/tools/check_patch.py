"""Execute the actual patched helpers with fixtures, without an Odoo runtime."""
import ast
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
tree = ast.parse((ROOT / 'controllers/portal_prepare.py').read_text())
class ValidationError(Exception): pass
class Expression:
    @staticmethod
    def AND(parts): return sum(parts, [])

namespace = {'ValidationError': ValidationError, '_': lambda value: value,
             'expression': Expression(), 'BASE': '/my/employee/purchase', 'json': json}
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
           {'_choice', '_scope', '_json', 'preview', 'product_defaults'}]
for method in methods: method.decorator_list = []
new_cls = ast.ClassDef(name='Service', bases=[], keywords=[], body=methods, decorator_list=[])
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'integer']
exec(compile(ast.fix_missing_locations(ast.Module(body=functions+[new_cls], type_ignores=[])), 'patch', 'exec'), namespace)
integer = namespace['integer']
assert integer(False) == integer(None) == integer('') == 0
for invalid in [True, -1, 'NewId_3', [1], 1.5]:
    try: integer(invalid)
    except ValidationError: pass
    else: raise AssertionError(invalid)

service = namespace['Service']()
class Model:
    def browse(self): return []
    def search(self, *args, **kwargs): return []
service._scope = lambda *args: (Model(), [], 'name')
assert service._choice('project', False, None) == []
for value, required in [(0, True), (42, True), ('NewId_42', True)]:
    try: service._choice('project', value, None, required)
    except ValidationError as exc: assert 'project' in str(exc)
    else: raise AssertionError('Unavailable project must be rejected')

class ScopedModel:
    _fields = {'company_id'}
    def sudo(self): return self
    def with_company(self, company): return self
models = {name: ScopedModel() for name in ['project.project', 'material.request']}
scope = namespace['Service'](); scope._env = lambda company: models
for kind in ['project', 'mr']:
    model, domain, order = scope._scope(kind, NS(id=7))
    assert ('company_id', '=', 7) in domain
    assert not any(item[0] in ['id', 'project_id'] and item[1] == 'in'
                   for item in domain if isinstance(item, tuple))
    if kind == 'mr':
        assert ('state', '=', 'approved') in domain
        assert ('no_po_required', '=', False) in domain
        assert ('employee_id.company_id', '=', 7) in domain

# Exercise preview ordering: all rows attached, line amounts recomputed, then
# native order tax totals. No create()/write() exists on these fixtures.
calls = []
class Lines(list):
    def _compute_amount(self): calls.append('line_amounts')
class Virtual:
    currency_id = NS(name='SAR')
    @property
    def order_line(self): return self.lines
    @order_line.setter
    def order_line(self, commands):
        self.lines = Lines(commands); calls.append('attach')
    def _amount_all(self):
        assert calls == ['attach', 'line_amounts']
        calls.append('order_totals')
        self.amount_untaxed, self.amount_tax, self.amount_total = 5000, 750, 5750
preview = namespace['Service'](); preview._actor = lambda *a: None
preview._company = lambda *a: NS(id=7)
preview._header = lambda *a: {}
preview._env = lambda *a: {'purchase.order': ScopedModel()}
preview._native_order = lambda *a: Virtual()
preview._line = lambda data, *a, **kw: data
preview._serialize_line = lambda row: row[2]
preview._json = lambda run: run({'company_id': 7, 'lines': [{'price_unit': 5000, 'product_qty': 1}]})
result = preview.preview()
assert result['total'] == 5750 and calls[-1] == 'order_totals'
assert result['lines'][0]['price_unit'] == 5000

# Product defaults from delegated pseudo-records must expose origin integers.
class ProductModel(ScopedModel):
    def default_get(self, names): return {}
    def new(self, values):
        relation = lambda ident: NS(id='NewId_%s' % ident, _origin=NS(id=ident), display_name='Selection')
        return NS(categ_id=relation(1), uom_id=relation(2), uom_po_id=relation(2),
                  purchase_method='receive', supplier_taxes_id=[relation(3)])
product = namespace['Service'](); product._actor = lambda *a: None
product._company = lambda *a: NS(id=7)
product._env = lambda *a: {'product.product': ProductModel()}
product._json = lambda run: run({'company_id': 7})
result = product.product_defaults()
assert result['categ_id']['id'] == 1 and result['uom_id']['id'] == 2
assert result['supplier_taxes'][0]['id'] == 3

# Both expected validation and unexpected server errors leave the savepoint
# through its exception path before a JSON error response is returned.
rollbacks, logged = [], []
class HTTPException(Exception): code = 403
class Cursor:
    @contextmanager
    def savepoint(self):
        try: yield
        except Exception:
            rollbacks.append(True)
            raise
namespace.update(AccessError=type('AccessError', (Exception,), {}),
                 UserError=type('UserError', (Exception,), {}), HTTPException=HTTPException,
                 uuid=NS(uuid4=lambda: NS(hex='123456789abcdef')),
                 _logger=NS(exception=lambda *args: logged.append(args)),
                 request=NS(env=NS(cr=Cursor()), params={'payload': '{}'},
                            httprequest=NS(path='/my/employee/purchase/save'),
                            make_json_response=lambda body, status=200: (body, status)))
json_service = namespace['Service']()
def fail(error): raise error
for error, status in [(ValidationError('Select a product'), 400),
                      (HTTPException(), 403), (RuntimeError('private database detail'), 500)]:
    body, actual_status = json_service._json(lambda data: fail(error))
    assert actual_status == status and body['error']
    assert 'private database detail' not in body['error']
assert len(rollbacks) == 3 and len(logged) == 1

# Translation must never be assigned a local loop/unpack target in a controller.
for path in (ROOT / 'controllers').glob('*.py'):
    for node in ast.walk(ast.parse(path.read_text())):
        assert not (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == '_'), path
print('PASS: optional IDs, translated validation, company project/MR scope, preview recomputation, product origin IDs and error rollback/JSON responses (isolated fixtures).')
