"""Execute actual scoped sales line validators/save gateway with ORM-shaped fixtures."""
import ast,json,pytz
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as N
from contextlib import nullcontext
class AccessError(Exception):pass
class UserError(Exception):pass
class ValidationError(Exception):pass
class Forbidden(Exception):pass
class NotFound(Exception):pass
root=Path(__file__).parents[1]
tree=ast.parse((root/'controllers/sales_lines.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
legacy=ast.parse((root/'controllers/portal_sales.py').read_text());num=next(n for c in legacy.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='_num');cls.body.append(num)
for name in ('_sales_date_local','_sales_date_utc'):
    cls.body.append(next(n for c in legacy.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name==name))
commands=N(set=lambda ids:(6,0,ids),create=lambda vals:(0,0,vals),update=lambda rid,vals:(1,rid,vals),delete=lambda rid:(2,rid,0))
ns=dict(json=json,pytz=pytz,datetime=datetime,Command=commands,_=lambda s:s,AccessError=AccessError,UserError=UserError,ValidationError=ValidationError,Forbidden=Forbidden,NotFound=NotFound,expression=N(AND=lambda d:d,OR=lambda d:d))
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'actual sales lines','exec'),ns)
s=ns['SalesLinesMixin']()
class Lines(list):
    @property
    def ids(self):return [l.id for l in self]
    def sorted(self,key):return Lines(sorted(self,key=(lambda l:getattr(l,key)) if isinstance(key,str) else key))
    def invalidate_recordset(self):pass
order=N(id=5,company_id=N(id=7),write_date='o1',absar_portal_creator_id=True,order_line=Lines([N(id=1,write_date='l1',product_id=True,display_type=False),N(id=2,write_date='l2',product_id=True,display_type=False)]))
order.invalidate_recordset=lambda:None
writes=[];order.write=lambda vals:writes.append(vals)
s._editable=lambda o:None;s._order=lambda rid:order if rid==5 else (_ for _ in ()).throw(NotFound())
choices=[]
def choice(o,kind,rid):
    choices.append((o.company_id.id,kind,rid))
    if rid==999:raise AccessError('Outside company')
    return N(id=rid,uom_id=N(category_id=1),category_id=1,plan_id=N(root_id=N(id=2 if rid in (10,11) else 3)))
s._line_choice=choice
row=dict(id=1,name='Negotiated',product_id=3,uom_id=1,quantity=4,price_unit=25,discount=5,taxes_id=[15,15],analytic_distribution={'10':100},order_id=999,company_id=999,arbitrary='blocked')
vals=s._line_values(order,row)
assert vals['tax_id']==[(6,0,[15])] and vals['analytic_distribution']=={'10':100}
assert not {'order_id','company_id','id','arbitrary','state'}.intersection(vals)
assert all(company==7 for company,kind,rid in choices)
for patch in [dict(quantity=0),dict(price_unit='nan'),dict(price_unit='inf'),dict(discount=101),dict(taxes_id=[999]),dict(product_id=999),dict(analytic_distribution={'10':50}),dict(analytic_distribution={'10,11':100}),dict(analytic_distribution={'10,10':100}),dict(analytic_distribution={'10':0})]:
    try:s._line_values(order,dict(row,**patch))
    except (UserError,ValidationError,AccessError):pass
    else:raise AssertionError(patch)
assert s._line_analytic(order,{'10,12':100})=={'10,12':100}
assert s._line_analytic(order,{'10':50,'11':50})=={'10':50,'11':50}
for value in (True,0,-1,'1.5'):
    try:s._line_id(value)
    except ValidationError:pass
    else:raise AssertionError(value)
assert ('company_id','=',7) in s._line_scope(order,'tax')[1]
assert ('type_tax_use','in',['sale','none']) in s._line_scope(order,'tax')[1]
assert ('company_ids','in',7) in s._line_scope(order,'income-account')[1]
locks=[]
request=N(env=N(cr=N(execute=lambda sql,args:locks.append((sql,args)),savepoint=lambda:nullcontext()),uid=4),httprequest=N(content_length=100),make_json_response=lambda payload,status=200:N(payload=payload,status=status))
ns['request']=request;s._line_boot=lambda o:{'saved':True}
def save(rows,version=None):return s._line_api(5,'save',{'payload':json.dumps({'lines':rows,'version':version or s._line_version(order),'company_id':999})})
result=save([row]);assert result.status==200 and result.payload['result']['saved']
assert writes[-1]['order_line'][0][0:2]==(1,1) and writes[-1]['order_line'][1]==(2,2,0)
assert len(locks)==2 and all(args==[5] for sql,args in locks)
for badrows,version in [([row],'old'),([dict(row,id=999)],None),([row,row],None),([dict(row,product_id=0)],None),([dict(row,display_type='line_note')],None)]:
    count=len(writes);r=save(badrows,version);assert r.status==400 and len(writes)==count
s._editable=lambda o:(_ for _ in ()).throw(Forbidden('Not an editable draft'))
count=len(writes);assert save([row]).status==400 and len(writes)==count
print('PASS: actual sales validators and gateway: company/tax/income-account scope, fixed fields, finite quantities/prices, plan totals/composites, version and row locks, exact line ownership, duplicate/type/deletion handling, readonly rejection (ORM fixtures).')
# Product updates use exact fields/locks and preserve taxes from other companies.
class Taxes(list):
    @property
    def ids(self):return [x.id for x in self]
    def filtered(self,fn):return Taxes(x for x in self if fn(x))
company=order.company_id
product=N(id=3,write_date='p1',product_tmpl_id=N(id=30,write_date='t1',invalidate_recordset=lambda:None),display_name='Product A',
          taxes_id=Taxes([N(id=15,company_id=company),N(id=90,company_id=N(id=99))]),invalidate_recordset=lambda:None)
product_writes=[];product.write=lambda vals:product_writes.append(vals)
products=N(create=lambda vals:(product_writes.append(vals) or product))
s._editable=lambda o:None;s._line_env=lambda o:{'product.product':products}
original_choice=s._line_choice
s._line_choice=lambda o,kind,rid:product if kind=='product' and rid==3 else original_choice(o,kind,rid)
payload=dict(id=3,version='p1|t1',name='Changed',type='consu',categ_id=1,uom_id=1,list_price=55,income_account_id=8,taxes_id=[15],
             company_id=999,sale_ok=False,purchase_ok=False,arbitrary='blocked')
r=s._line_product(order,'product-update',payload)
assert r['product_updated'] and product_writes[-1]['taxes_id']==[(6,0,[15,90])]
assert not {'company_id','sale_ok','purchase_ok','arbitrary','id','version'}.intersection(product_writes[-1])
for patch in [dict(version='old'),dict(income_account_id=999),dict(taxes_id=[999]),dict(list_price='nan')]:
    count=len(product_writes)
    try:s._line_product(order,'product-update',dict(payload,**patch))
    except (UserError,AccessError,ValidationError):pass
    else:raise AssertionError(patch)
    assert len(product_writes)==count
s._line_product(order,'product-create',dict(payload,id=None))
assert product_writes[-1]['company_id']==7 and product_writes[-1]['sale_ok'] and product_writes[-1]['purchase_ok'] is False
print('PASS: actual sales product form update whitelist, template/variant locks, version conflict, finite price, scoped income/tax choices, company-specific creation and other-company tax preservation.')
# Accounting enforces the same Purchase per-plan allocation rules on the server.
accounting=ast.parse((root.parent/'absar_portal_accounting/models/service.py').read_text())
fn=next(n for c in accounting.body if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='_analytic')
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'actual accounting analytic','exec'),ns)
def relation(c,model,rid,domain,required):
    assert ('company_id','=',7) in domain
    return original_choice(order,'analytic',rid)
actor=N(_id=s._line_id,_number=s._num,_relation=relation)
assert ns['_analytic'](actor,company,{'10,12':100})=={'10,12':100}
assert ns['_analytic'](actor,company,{'10':50,'11':50})=={'10':50,'11':50}
for raw in ({'10':50},{'10,11':100},{'10':0},{'10,12':50,'12,10':50},{'999':100}):
    try:ns['_analytic'](actor,company,raw)
    except (ValidationError,UserError,AccessError):pass
    else:raise AssertionError(raw)
assert (root/'static/src/js/purchase_ui.js').read_bytes()==(root.parent/'absar_portal_purchase_monitor/static/src/js/purchase_ui.js').read_bytes()
assert (root/'static/src/js/purchase_ui.js').read_bytes()==(root.parent/'absar_portal_accounting/static/src/purchase_ui.js').read_bytes()
assert (root/'static/src/js/analytic_editor.js').read_bytes()==(root.parent/'absar_portal_accounting/static/src/analytic_editor.js').read_bytes()
print('PASS: Accounting and Sales share identical Purchase UI helpers/allocation editor; Accounting validates plan totals, duplicate plans/rows and company scope.')
# New quotations use the same scoped line gateway before their first database save.
from datetime import date
ns['fields']=N(Date=N(to_date=date.fromisoformat),Datetime=N(now=lambda:datetime(2026,10,21,12),to_datetime=lambda value:value))
created=[]
company=N(id=7);partner=N(id=21,company_id=False);project=N(id=31,company_id=company)
class Browse:
    def sudo(self):return self
    def __init__(self,rows):self.rows=rows;self.current=None
    def browse(self,rid):self.current=self.rows.get(rid);return self
    def exists(self):return self.current
class Orders:
    def new(self,vals):return N(id=False,company_id=company,partner_id=partner,order_line=Lines([]),values=vals)
    def sudo(self):return self
    def with_company(self,c):return self
    def create(self,vals):created.append(vals);return N(id=55)
class Env(dict):
    user=N(tz='Europe/Berlin')
    uid=4
    cr=request.env.cr
request.env=Env({'res.partner':Browse({21:partner,99:N(id=99,company_id=N(id=99))}),
                 'project.project':Browse({31:project}), 'sale.order':Orders()})
s._allowed=lambda:N(company_id=company,id=4)
s._partners=lambda limit=None:[partner]
s._customer_projects=lambda p:[project]
s._line_env=lambda o:request.env
s._line_choice=original_choice
s._line_boot=lambda o:{'saved':True}
def create(header,rows):return s._line_api(None,'create',{'payload':json.dumps({'header':header,'lines':rows})})
header=dict(partner_id=21,project_id=31,kind='standard',date_order='2026-10-21T15:30:00',validity_date='2026-11-01',company_id=99,state='sale',absar_order_review_state='approved')
r=create(header,[dict(row,id=0)]);assert r.status==200 and r.payload['result']['redirect'].endswith('/55')
assert created[-1]['company_id']==7 and created[-1]['absar_portal_creator_id']==4 and created[-1]['order_line'][0][0]==0
assert not {'state','absar_order_review_state'}.intersection(created[-1])
assert created[-1]['date_order']==datetime(2026,10,21,13,30)
for patch,rows in [({'date_order':''},[]),({'date_order':'bad'},[]),({'partner_id':0},[]),({'partner_id':99},[]),({'project_id':999},[]),({'kind':'bad'},[]),({'validity_date':'invalid'},[]),({},[row]),({},[dict(row,id=0,price_unit='nan')])]:
    count=len(created);result=create(dict(header,**patch),rows);assert result.status==400 and len(created)==count
print('PASS: new quotation header and lines save together; customer/project/company/date/type checks and forged state/approval/foreign-line fields rejected (ORM fixtures).')

assert s._sales_date_local(datetime(2026,10,21,13,30))=='2026-10-21T15:30:00'
for value in ('', 'bad','2026-10-25T02:30:00','2026-03-29T02:30:00','2026-10-21T15:30:00+02:00'):
    try:s._sales_date_utc(value)
    except ValidationError:pass
    else:raise AssertionError(value)
print('PASS: quotation/order date uses the employee timezone; empty, invalid, ambiguous/nonexistent DST and offset-bearing input rejected.')
# Existing drafts save header and lines atomically and use the unsaved date for pricing.
order.partner_id=partner;order.absar_proposal_type='standard'
order.pricelist_id=N(id=43);order.currency_id=N(id=44);order.fiscal_position_id=N(id=45);order.date_order=datetime(2026,10,21,12)
combined=dict(header,partner_id=99,company_id=99,state='sale')
values=s._line_header_values(order,combined)
assert values['date_order']==datetime(2026,10,21,13,30) and values['construction_project_id']==31
assert not {'state','company_id','partner_id','absar_order_review_state'}.intersection(values)
assert s._line_pricing_values(order,{'header':combined})['date_order']==datetime(2026,10,21,13,30)
count=len(writes)
r=s._line_api(5,'save',{'payload':json.dumps({'header':combined,'version':s._line_version(order),'lines':[row]})})
assert r.status==200 and len(writes)==count+1
assert 'order_line' in writes[-1] and writes[-1]['date_order']==datetime(2026,10,21,13,30)
for patch in ({'date_order':''},{'date_order':'bad'},{'project_id':999}):
    count=len(writes)
    r=s._line_api(5,'save',{'payload':json.dumps({'header':dict(combined,**patch),'version':s._line_version(order),'lines':[row]})})
    assert r.status==400 and len(writes)==count
print('PASS: existing quotation saves details + lines in one write; unsaved date drives pricing; invalid dates/projects and forged header fields cannot bypass validation.')
