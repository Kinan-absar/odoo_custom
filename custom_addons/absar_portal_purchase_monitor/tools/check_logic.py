"""Isolated checks of actual addon validators; not an Odoo installation test."""
import ast
import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS
import pytz

ROOT = Path(__file__).resolve().parents[1]
class ValidationError(Exception): pass
class AccessError(Exception): pass
class UserError(Exception): pass

def extract(path, class_name, names, globals_):
    tree = ast.parse(path.read_text())
    selected = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    methods = [n for n in selected.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for method in methods: method.decorator_list = []
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, str(path), 'exec'), globals_)
    return globals_[class_name]

g = dict(math=math, datetime=datetime, pytz=pytz, ValidationError=ValidationError,
         AccessError=AccessError, UserError=UserError, _=lambda s:s)
source = ast.parse((ROOT/'controllers/portal_prepare.py').read_text())
fns = [n for n in source.body if isinstance(n,ast.FunctionDef)]
exec(compile(ast.fix_missing_locations(ast.Module(body=fns,type_ignores=[])),'validators','exec'),g)
Service=extract(ROOT/'controllers/portal_prepare.py','PortalPurchasePrepare',{'_analytic','_utc'},g)
service=Service()
def account(ident, plan): return NS(id=ident,plan_id=NS(root_id=NS(id=plan)))
accounts={1:account(1,10),2:account(2,10),3:account(3,20),4:account(4,20)}
def choice(kind, ident, company, required):
    if ident not in accounts: raise ValidationError('Unavailable account/company')
    return accounts[ident]
service._choice=choice
checks=0

def ok(condition):
    global checks
    assert condition; checks+=1

def rejects(fn):
    global checks
    try: fn()
    except (ValidationError,UserError,AccessError): checks+=1; return
    raise AssertionError('Expected rejection')

ok(service._analytic({'1':60,'2':40},1)=={'1':60.0,'2':40.0})
ok(service._analytic({'1,3':60,'2,4':40},1)=={'1,3':60.0,'2,4':40.0})
ok(service._analytic({'1':100,'3':100},1)=={'1':100.0,'3':100.0})
ok(service._analytic({},1)=={})
for raw in ({'1':90},{'1':110},{'1':0},{'1':-10},{'1':'nan'},{'1':float('inf')},
            {'1,2':100},{'1,1':100},{'1,3':100,'3,1':100},{'999':100},
            {'0':100},{'bad':100},[],{'1':60,'2':60}):
    rejects(lambda raw=raw:service._analytic(raw,1))
for value in ['nan','inf','-inf',None,'bad',float('nan')]: rejects(lambda value=value:g['number'](value,'test'))
ok(g['number']('12.75','test')==12.75)
for value in [-1,True,1.9,'1 OR 1=1','bad']: rejects(lambda value=value:g['integer'](value))
ok(g['integer']('42')==42)
g['request']=NS(env=NS(user=NS(tz='Europe/Berlin')))
ok(service._utc('2026-10-17T19:00:00')==datetime(2026,10,17,17))
rejects(lambda:service._utc('2026-10-25T02:30:00'))
rejects(lambda:service._utc('2026-03-29T02:30:00'))
rejects(lambda:service._utc('invalid'))
rejects(lambda:service._utc('2026-10-17T19:00:00+02:00'))
ok(service._utc('') is False)

# Single-step purchase approval and role composition are exercised separately by
# check_purchase_policy.py, including the actual changed addon methods.
print(f'{checks} isolated validator checks passed. No Odoo ORM or browser integration tested.')

# Financial integration checks execute the actual monitoring calculation with
# recordset-shaped fixtures; ORM searches/permissions remain staging-only tests.
Monitor=extract(ROOT/'controllers/portal_purchase.py','PortalPurchaseMonitor',{'_rows'},g)
class Records(list):
    @property
    def ids(self):return [r.id for r in self]
    def filtered(self,fn):return Records(r for r in self if fn(r))
    def mapped(self,name):return [getattr(r,name) for r in self]
    def __getattr__(self,name):
        result=[]
        for record in self:
            val=getattr(record,name)
            values=list(val) if isinstance(val,Records) else [val]
            for value in values:
                if value not in result:result.append(value)
        return Records(result)
class Currency:
    def __init__(self,name,rate):self.name=name;self.rate=rate
    def _convert(self,value,target,company,date):return value*self.rate/target.rate
    def round(self,value):return round(value,2)
sar=Currency('SAR',1);usd=Currency('USD',3.75)
company=NS(currency_id=sar)
def move(ident, amounts, residual, currency=sar, kind='in_invoice', state='posted'):
    doc=NS(id=ident,state=state,move_type=kind,currency_id=currency,amount_total=sum(amounts),amount_residual=residual,invoice_date='2026-10-17',date='2026-10-17')
    doc.invoice_line_ids=Records(NS(id=ident*100+i,move_id=doc,price_total=value,display_type='product') for i,value in enumerate(amounts))
    return doc
def po(ident,lines,amount=1000,paid=50,currency=sar,paid_currency_field='currency_id'):
    return NS(id=ident,order_line=NS(invoice_lines=Records(lines)),company_id=company,
              currency_id=currency,amount_total=amount,amount_paid=paid,
              signature_status_text='1/2 Signed · Waiting: CEO',
              project_id=NS(display_name='Project'),material_request_id=NS(display_name='MR'),
              _fields={'signature_status_text':True,'project_id':True,'amount_paid':NS(currency_field=paid_currency_field)},
              __class__=object)
# Native records support po[field] for Monetary.currency_field.
class PO:
    def __init__(self,fixture):self.__dict__.update(fixture.__dict__)
    def __getitem__(self,key):return getattr(self,key)
bill=move(1,[120,40],80)
refund=move(2,[20],0,kind='in_refund')
pending=move(3,[999],999,state='draft')
p1=PO(po(1,[bill.invoice_line_ids[0],refund.invoice_line_ids[0],pending.invoice_line_ids[0]]))
p2=PO(po(2,[bill.invoice_line_ids[1]],paid=0))
r1,r2=Monitor()._rows([p1,p2])
ok((r1['billed'],r1['due'],r1['settled'],r1['paid'])==(100,60,40,50))
ok((r2['billed'],r2['due'],r2['settled'])==(40,20,20))
ok(r1['allocated'] and r2['allocated'])
ok(r1['signature']=='1/2 Signed · Waiting: CEO')
usdbill=move(4,[100],20,currency=usd)
r=Monitor()._rows([PO(po(3,list(usdbill.invoice_line_ids)))])[0]
ok((r['billed'],r['due'],r['settled'])==(375,75,300))
r=Monitor()._rows([PO(po(4,[],amount=1000,paid=150))])[0]
ok((r['billed'],r['due'],r['paid'],r['unbilled'])==(0,0,150,1000))
p=PO(po(5,[],currency=usd,paid_currency_field='company_currency_id'));p.company_currency_id=sar
ok(Monitor()._rows([p])[0]['paid'] is None)
print(f'{checks} total isolated validation, workflow and financial checks passed.')
