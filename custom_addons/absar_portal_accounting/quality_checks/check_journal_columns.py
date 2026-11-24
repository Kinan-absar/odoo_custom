"""Execute actual journal value and analytic-name helpers with scoped fixtures."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
class AccessError(Exception):pass
class ValidationError(Exception):pass
source=Path(__file__).parents[1]/'models'/'service.py'
tree=ast.parse(source.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('_move_values','_analytic_name_map')]
node=ast.ClassDef(name='Service',bases=[],keywords=[],body=methods,decorator_list=[])
ns=dict(AccessError=AccessError,ValidationError=ValidationError,_=lambda s:s,Command=NS(create=lambda v:(0,0,v),set=lambda ids:(6,0,ids)))
exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),ns)
s=ns['Service']();currency=NS(id=1,is_zero=lambda n:abs(n)<.001);company=NS(id=7,currency_id=currency,account_fiscal_country_id=NS(id=99))
s._kind=lambda kind:('account.move','Journals','entry')
s._journal=lambda *args:NS(id=2);s._partner=lambda *args:NS(id=3)
s._relation=lambda *args:currency;s._date=lambda value,*args:value or False
s._account=lambda *args:NS(id=8);s._analytic=lambda company,distribution:distribution or {};s._number=lambda n,*args:float(n or 0)
selected=[]
def m2m(company,model,ids,domain):
    selected.append((model,ids,domain))
    if 999 in ids:raise AccessError('Out of scope')
    assert (('company_id','=',7) in domain if model=='account.tax' else ('country_id','=',99) in domain)
    return NS(ids=ids)
s._m2m=m2m
payload={'date':'2026-10-21','journal_id':2,'lines':[
    {'name':'Expense','account_id':8,'debit':100,'credit':0,'taxes_id':[15],'tax_tag_ids':[4],'analytic_distribution':{'5':100}},
    {'name':'Accrual','account_id':9,'debit':0,'credit':100,'taxes_id':[],'tax_tag_ids':[]}]}
vals=s._move_values(company,'journals',payload)
first=vals['line_ids'][0][2]
assert first['tax_ids']==[(6,0,[15])] and first['tax_tag_ids']==[(6,0,[4])]
assert first['analytic_distribution']=={'5':100}
assert ('type_tax_use','in',['purchase','sale','none']) in next(d for m,ids,d in selected if m=='account.tax')
for key in ('taxes_id','tax_tag_ids'):
    payload['lines'][0][key]=[999]
    try:s._move_values(company,'journals',payload)
    except AccessError:pass
    else:raise AssertionError(key)
    payload['lines'][0][key]=[15] if key=='taxes_id' else [4]
queries=[]
def search(domain):
    queries.append(domain)
    assert ('company_id','=',7) in domain and ('company_id','=',False) in domain
    assert ('id','in',[5,6]) in domain
    return [NS(id=5,display_name='PHC'),NS(id=6,display_name='Division 03')]
s._env=lambda company:{'account.analytic.account':NS(search=search)}
assert s._analytic_name_map(company,[{'5,6':100},{'5':50},{}])=={'5':'PHC','6':'Division 03'}
assert len(queries)==1
print('PASS: actual journal tax/grid serialization and scope, analytic preservation, scoped composite analytic name map (ORM fixtures).')
