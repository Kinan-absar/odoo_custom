"""Execute scoped product update/whitelist code with fixtures, not the ORM."""
import ast, math
from pathlib import Path
from types import SimpleNamespace as N
R=Path(__file__).resolve().parents[1]
class ValidationError(Exception):pass
class UserError(Exception):pass
class AccessError(Exception):pass
ctx={'_':lambda s:s,'ValidationError':ValidationError,'UserError':UserError,'AccessError':AccessError,'math':math}
tree=ast.parse((R/'controllers/portal_prepare.py').read_text())
fns=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('integer','number')]
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('_product_values','_product_version','update_product','create_product')]
for n in methods:n.decorator_list=[]
module=ast.fix_missing_locations(ast.Module(body=fns+[ast.ClassDef(name='Service',bases=[],keywords=[],body=methods,decorator_list=[])],type_ignores=[]))
exec(compile(module,'product helpers','exec'),ctx)
S=ctx['Service'];company=N(id=7);other=N(id=8)
class Taxes(list):
 def filtered(self,p):return Taxes(t for t in self if p(t))
 @property
 def ids(self):return [t.id for t in self]
class Product:
 id=9;write_date='variant-v1';display_name='Product';_fields={'is_storable'}
 product_tmpl_id=N(id=19,write_date='template-v1',invalidate_recordset=lambda:None)
 supplier_taxes_id=Taxes([N(id=3,company_id=company),N(id=90,company_id=other)])
 property_account_expense_id=N(display_name='Expense');categ_id=N(property_account_expense_categ_id=N(display_name='Category Expense'))
 def with_company(self,c):assert c==company;return self
 def invalidate_recordset(self):pass
 def sudo(self):return self
 def write(self,vals):self.written=vals
product=Product();s=S();s._env=lambda c:{'product.product':product}
choices=[]
def choice(kind,id,c,required=False):
 choices.append((kind,id,c.id,required))
 if id==999:raise AccessError('outside company')
 if kind=='product':return product
 return N(id=id or False,category_id=1)
s._choice=choice;s._company=lambda id:company;s._actor=lambda role:role
calls=[];ctx['request']=N(env=N(cr=N(execute=lambda query,args:calls.append((query,args)))))
payload={'name':'Test','type':'consu','categ_id':1,'uom_id':2,'uom_po_id':2,'supplier_taxes_id':[3,3],
 'company_id':7,'property_account_expense_id':6,'standard_price':10,'id':9,'version':'variant-v1|template-v1',
 'sale_ok':False,'company_ids':[999],'arbitrary_field':'not allowed'}
s._json=lambda run:run(payload)
vals=s._product_values(payload,company)
assert vals['supplier_taxes_id']==[(6,0,[3])]
assert vals['property_account_expense_id']==6 and 'arbitrary_field' not in vals and 'company_ids' not in vals
result=s.update_product();assert result['product_updated'] and result['default_account']=='Expense'
assert product.written['supplier_taxes_id']==[(6,0,[3,90])]
assert not {'company_id','sale_ok','purchase_ok','arbitrary_field','company_ids'}.intersection(product.written)
assert len(calls)==2 and calls[0][1]==[19] and calls[1][1]==[9]
payload['property_account_expense_id']=0
assert s._product_values(payload,company)['property_account_expense_id'] is False
for patch,exc in [({'version':'old'},UserError),({'property_account_expense_id':999},AccessError),({'standard_price':'nan'},ValidationError),({'standard_price':-1},ValidationError),({'type':'other'},ValidationError)]:
 old=dict(payload);payload.update(patch)
 try:s.update_product()
 except exc:pass
 else:raise AssertionError(patch)
 payload.clear();payload.update(old)
s._actor=lambda role:(_ for _ in ()).throw(AccessError('role'))
try:s.update_product()
except AccessError:pass
else:raise AssertionError('non-issuer edit allowed')
print('PASS: product update role gate, company-scoped choice validation, stale version rejection, row locks, finite cost, whitelist, account clearing, tax deduplication and other-company tax preservation (isolated fixtures).')
