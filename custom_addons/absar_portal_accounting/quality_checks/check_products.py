"""Run actual accounting product gateway methods with scoped ORM fixtures."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace as NS
class AccessError(Exception):pass
class UserError(Exception):pass
class ValidationError(Exception):pass
class Taxes(list):
    @property
    def ids(self):return [t.id for t in self]
    def filtered(self,fn):return Taxes(t for t in self if fn(t))
company=NS(id=1,portal_accounting_journal_ids=[1]);other=NS(id=2)
class Product:
    id=9;write_date='v1';display_name='Cement';name='Cement';company_id=False;type='consu';is_storable=False
    product_tmpl_id=NS(id=19,write_date='t1',invalidate_recordset=lambda:None)
    supplier_taxes_id=Taxes([NS(id=15,name='VAT',company_id=company),NS(id=90,name='Other',company_id=other)])
    def invalidate_recordset(self):pass
    def write(self,vals):self.written=vals
product=Product()
class Products:
    def browse(self):return None
    def create(self,vals):product.written=vals;return product
source=Path(__file__).parents[1]/'models'/'product_service.py'
tree=ast.parse(source.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
cls.bases=[]
namespace=dict(AccessError=AccessError,UserError=UserError,ValidationError=ValidationError,_=lambda s:s,Command=NS(set=lambda ids:(6,0,ids)))
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),str(source),'exec'),namespace)
s=namespace['AccountingProducts']();s._env=lambda c:{'product.product':Products()}
actor_roles=[]
s._actor=lambda role=None, kind=None:(actor_roles.append(role) or (NS(id=1),{'preparer':True}))
s._kind=lambda kind: None if kind in ('bills','refunds','invoices') else (_ for _ in ()).throw(AccessError())
choices=[]
def relation(c,model,rid,domain,required=False):
    choices.append((model,rid,domain))
    if rid==999:raise AccessError('outside company')
    if model=='product.product':return product
    return NS(id=rid or False,category_id=99 if rid==88 else 1)
s._relation=relation
s._account=lambda c,rid,required=False:relation(c,'account.account',rid,[],required)
def taxes(c,model,ids,domain):
    assert ('company_id','=',1) in domain and ('type_tax_use','in',['purchase','none']) in domain
    if 999 in ids:raise AccessError()
    return Taxes(NS(id=i) for i in ids)
s._m2m=taxes
s._product_selection=lambda p,c:{'id':p.id,'name':p.name}
def number(value):
    v=float(value or 0)
    if not math.isfinite(v):raise ValidationError()
    return v
s._number=number
locks=[];s.env=NS(cr=NS(execute=lambda sql,args:locks.append((sql,args))))
payload=dict(id=9,version='v1|t1',name='Edited',type='consu',categ_id=1,uom_id=2,uom_po_id=2,
    purchase_method='receive',supplier_taxes_id=[15,15],standard_price=20,property_account_expense_id=8,
    arbitrary_field='blocked',company_id=999,sale_ok=False,purchase_ok=False)
result=s._product_operation(company,'bills','product-update',payload)
assert result['product_updated'] and actor_roles[-1]=='preparer'
assert product.written['supplier_taxes_id']==[(6,0,[15,90])]
assert not {'company_id','sale_ok','purchase_ok','arbitrary_field','id','version'}.intersection(product.written)
assert locks[0][1]==[19] and locks[1][1]==[9]
assert any(model=='product.product' and ('company_id','=',1) in domain for model,rid,domain in choices)
clear=dict(payload,property_account_expense_id=False)
s._product_operation(company,'refunds','product-update',clear)
assert product.written['property_account_expense_id'] is False
for patch,error in [({'version':'stale'},UserError),({'id':999},AccessError),({'property_account_expense_id':999},AccessError),({'supplier_taxes_id':[999]},AccessError),({'standard_price':'nan'},ValidationError),({'standard_price':-1},ValidationError),({'uom_po_id':88},ValidationError),({'type':'bad'},ValidationError)]:
    try:s._product_operation(company,'bills','product-update',dict(payload,**patch))
    except error:pass
    else:raise AssertionError(patch)
for kind,c in [('journals',company),('bills',NS(id=1,portal_accounting_journal_ids=[]))]:
    try:s._product_operation(c,kind,'product-update',payload)
    except AccessError:pass
    else:raise AssertionError('Unexpected workspace access')
s._product_operation(company,'bills','product-create',payload)
assert product.written['company_id']==1 and product.written['purchase_ok'] and product.written['sale_ok'] is False
s._actor=lambda role=None, kind=None:(_ for _ in ()).throw(AccessError('no preparer role'))
try:s._product_operation(company,'bills','product-update',payload)
except AccessError:pass
else:raise AssertionError('Unauthorized product edit')
print('PASS: actual product gateway role, workspace/company scope, row locks, stale edit, account clear, finite/nonnegative cost, UoM category, fixed field whitelist, company-scoped create and other-company tax preservation (ORM fixtures).')
