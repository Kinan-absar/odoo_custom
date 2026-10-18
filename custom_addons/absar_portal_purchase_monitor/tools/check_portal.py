"""Portal architecture and native-host withdrawal regression checks.

Executes the actual pre-migration SQL against disposable SQLite tables. This
verifies selection/scope and idempotency, not PostgreSQL/Odoo upgrade execution.
"""
import ast
import sqlite3
import importlib.util
from pathlib import Path
from lxml import etree

ROOT=Path(__file__).resolve().parents[1]
checks=0

def check(value):
 global checks
 assert value
 checks+=1

manifest=ast.literal_eval((ROOT/'__manifest__.py').read_text())
check(manifest['version']=='18.0.1.5.1')
check(set(manifest['assets'])=={'web.assets_frontend'})
check('assets_backend' not in repr(manifest))
check('security/ir.model.access.csv' not in manifest['data'])
check('native_access' not in (ROOT/'models/__init__.py').read_text())
check('native_workspace' not in (ROOT/'controllers/__init__.py').read_text())
check('native_product' not in (ROOT/'models/__init__.py').read_text())
check(not (ROOT/'security/ir.model.access.csv').exists())
for asset in manifest['assets']['web.assets_frontend']:
 check((ROOT.parent/asset).is_file())
check(not etree.parse(str(ROOT/'security/groups.xml')).xpath('//field[@name="implied_ids"]'))

spec=importlib.util.spec_from_file_location('retire_native_host',ROOT/'migrations/18.0.1.5.0/pre-migration.py')
migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
connection=sqlite3.connect(':memory:')
connection.executescript('''
 CREATE TABLE ir_model_data (module TEXT, model TEXT, name TEXT, res_id INTEGER);
 CREATE TABLE ir_model_access (id INTEGER PRIMARY KEY);
 CREATE TABLE ir_rule (id INTEGER PRIMARY KEY);
 CREATE TABLE ir_ui_view (id INTEGER PRIMARY KEY, active BOOLEAN);
 INSERT INTO ir_model_access VALUES (1),(2),(3),(4);
 INSERT INTO ir_rule VALUES (10),(11),(12);
 INSERT INTO ir_ui_view VALUES (20,1),(21,1),(22,1);
''')
owned='absar_portal_purchase_monitor'
connection.executemany('INSERT INTO ir_model_data VALUES (?,?,?,?)',[
 (owned,'ir.model.access','access_native_order',1),
 ('another_module','ir.model.access','access_native_order',2),
 (owned,'ir.model.access','access_other_purchase',3),
 (owned,'ir.model.access','accessXnativeYlookalike',4),
 (owned,'ir.rule','native_scope_order',10),
 ('another_module','ir.rule','native_scope_order',11),
 (owned,'ir.rule','nativeXlookalike',12),
 (owned,'ir.ui.view','product_form_native_presentation',20),
 ('another_module','ir.ui.view','product_form_native_presentation',21),
 (owned,'ir.ui.view','purchase_order_form_portal_review',22),
])
class Cursor:
 def execute(self,sql,params):return connection.execute(sql.replace('%s','?'),params)
cr=Cursor();migration.retire_native_host(cr)
check(connection.execute('SELECT id FROM ir_model_access ORDER BY id').fetchall()==[(2,),(3,),(4,)])
check(connection.execute('SELECT id FROM ir_rule ORDER BY id').fetchall()==[(11,),(12,)])
check(connection.execute('SELECT active FROM ir_ui_view ORDER BY id').fetchall()==[(0,),(1,),(1,)])
check(connection.execute('SELECT COUNT(*) FROM ir_model_data').fetchone()[0]==8)
# Second execution and a fresh install with no native metadata are harmless.
before=connection.iterdump(); snapshot=list(before);migration.retire_native_host(cr)
check(list(connection.iterdump())==snapshot)
connection.executescript('DELETE FROM ir_model_data; DELETE FROM ir_model_access; DELETE FROM ir_rule; DELETE FROM ir_ui_view;')
migration.retire_native_host(cr)
check(connection.execute('SELECT COUNT(*) FROM ir_model_access').fetchone()[0]==0)
# Every controller mutation has named routes, authentication and CSRF; no model/method dispatch input.
for filename in ['portal_prepare.py','portal_purchase.py','portal_directory.py']:
 tree=ast.parse((ROOT/'controllers'/filename).read_text())
 for node in ast.walk(tree):
  if not isinstance(node,ast.FunctionDef):continue
  for dec in node.decorator_list:
   if isinstance(dec,ast.Call) and isinstance(dec.func,ast.Attribute) and dec.func.attr=='route':
    kw={k.arg:ast.literal_eval(k.value) for k in dec.keywords}
    check(kw.get('auth')=='user')
    if kw.get('methods')==['POST']:check(kw.get('csrf') is True)
for path in (ROOT/'static/src/js').glob('*.js'):
 text=path.read_text()
 check('/web/dataset' not in text and 'call_kw' not in text and 'assets_backend' not in text)
# Approved/company-scoped MR lookup and no generic attachment target.
controller=(ROOT/'controllers/portal_prepare.py').read_text()
check("('state', '=', 'approved')" in controller)
check("('no_po_required', '=', False)" in controller)
check("self._projects" not in controller)
directory=(ROOT/'controllers/portal_directory.py').read_text()
check("attachment.res_model != 'purchase.order' or attachment.res_id != po.id" in directory)
check("'res_model': 'purchase.order', 'res_id': po.id" in directory)
check("po = self._record(po_id, edit=True)" in directory)
check("cost = number(data['standard_price']" in controller)
print(f'{checks} portal boundary, migration scope/idempotency and route checks passed. Odoo runtime not initialized.')

# Execute the actual post-migration guard, including a prefix lookalike which
# must not be treated as an owned native permission.
from types import SimpleNamespace as NS
post_tree=ast.parse((ROOT/'migrations/18.0.1.5.0/post-migration.py').read_text())
post_fn=next(n for n in post_tree.body if isinstance(n,ast.FunctionDef) and n.name=='migrate')
class Records(list):
 def filtered(self,predicate):return Records(row for row in self if predicate(row))
class Metadata:
 def search(self,domain):return Records(NS(name=name) for name in self.names)
metadata=Metadata();metadata.names=['access_other_purchase','accessXnativeYlookalike','nativeXlookalike']
class Environment:
 def __getitem__(self,key):return metadata
ns={'api':NS(Environment=lambda *args:Environment()),'SUPERUSER_ID':1}
exec(compile(ast.fix_missing_locations(ast.Module(body=[post_fn],type_ignores=[])),'post-migration','exec'),ns)
ns['migrate'](None,'18.0.1.4.2');check(True)
metadata.names.append('native_scope_order')
try:ns['migrate'](None,'18.0.1.4.2')
except RuntimeError:check(True)
else:raise AssertionError('Native grant must abort upgrade')
print('Post-migration prefix and fail-closed checks passed.')

# Execute the actual MR proposal method: unique matches, ambiguous names,
# incompatible units and unmapped materials must not create master records.
tree=ast.parse((ROOT/'controllers/portal_directory.py').read_text())
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PortalPurchaseDirectory')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_mr_data');method.decorator_list=[]
class ValidationError(Exception):pass
context={'expression':NS(AND=lambda groups:[term for group in groups for term in group]),'ValidationError':ValidationError,'_':lambda value:value}
probe=ast.ClassDef(name='Directory',bases=[],keywords=[],body=[method],decorator_list=[])
exec(compile(ast.fix_missing_locations(ast.Module(body=[probe],type_ignores=[])),'mr-proposal','exec'),context)
class ProductRows(list):
 def __getattr__(self,name):
  if not self:return False if name in ('id','display_name') else ProductRows()
  return getattr(self[0],name)
class ProductModel:
 def search(self,domain,limit):
  name=next(term[2] for term in domain if term[0]=='name')
  return ProductRows(products.get(name,[])[:limit])
 def browse(self):return ProductRows()
 def create(self,*args):raise AssertionError('Opening an MR must not create products')
uom=NS(id=7,display_name='Units',category_id=NS(id=1));wrong=NS(id=8,display_name='Metres',category_id=NS(id=2))
p=NS(id=44,display_name='Unique',uom_id=uom,uom_po_id=uom)
products={'Unique':[p],'Ambiguous':[p,p],'Wrong Unit':[p]}
service=context['Directory']();service._scope=lambda *args:(ProductModel(),[('company_id','=',1)],'name')
mr=NS(id=8,name='MR0008',project_id=NS(id=9,display_name='Assigned'),delivery_date='2026-12-01',line_ids=[
 NS(item_name='Unique',qty_required=5,uom_id=uom),NS(item_name='Ambiguous',qty_required=3,uom_id=uom),
 NS(item_name='Wrong Unit',qty_required=2,uom_id=wrong),NS(item_name='Unmapped',qty_required=4,uom_id=False)])
result=service._mr_data(mr,NS(id=1))
check(result['lines'][0]['product_id']==44)
check(result['lines'][0]['product_qty']==5 and result['lines'][0]['price_unit']==0)
check(result['lines'][1]['product_id'] is False or result['lines'][1]['product_id']==0)
check(result['lines'][2]['product_id'] is False or result['lines'][2]['product_id']==0)
check(result['lines'][3]['product_id'] is False or result['lines'][3]['product_id']==0)
check(result['lines'][2]['product_uom']==8)
check(result['project']['id']==9 and result['id']==8)
mr.line_ids=mr.line_ids[:1]*301
try:service._mr_data(mr,NS(id=1))
except ValidationError:check(True)
else:raise AssertionError('MR line cap missing')
print('8 MR proposal/matching/line-cap checks passed; no records created.')
