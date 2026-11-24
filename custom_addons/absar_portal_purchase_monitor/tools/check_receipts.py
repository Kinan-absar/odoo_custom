"""Actual receipt helper code on isolated recordset fixtures, not an Odoo ORM test."""
import ast,json,math
from pathlib import Path
from types import SimpleNamespace as N
R=Path(__file__).resolve().parents[1]
class UserError(Exception):pass
class ValidationError(Exception):pass
class AccessError(Exception):pass
class Records(list):
 @property
 def ids(self):return [r.id for r in self]
 def filtered(self,p):return Records(r for r in self if p(r))
 def sorted(self,key):return Records(sorted(self,key=lambda r:getattr(r,key)))
 def sudo(self):return self
 def with_company(self,c):return self
 def invalidate_recordset(self):pass
 def __contains__(self,x):return super().__contains__(x[0] if isinstance(x,Records) and len(x)==1 else x)
 def __getattr__(self,k):
  if k in ('move_ids','move_line_ids'):
   return Records(x for r in self for x in getattr(r,k))
  if len(self)==1:return getattr(self[0],k)
  raise AttributeError(k)
class Move:
 def __init__(self,po,id,qty=5,tracking='none'):
  self.id=id;self.state='assigned';self.write_date='mv1';self.quantity=qty;self.picked=False;self.product_uom_qty=qty
  self.product_id=N(tracking=tracking,display_name='Material '+str(id));self.product_uom=N(display_name='Units',rounding=.01)
  self.purchase_line_id=N(order_id=po,qty_received=0);self.move_line_ids=Records();self.name=self.product_id.display_name
 def sudo(self):return self
 def with_company(self,c):return self
 def write(self,v):self.__dict__.update(v)
class Picking:
 id=5;name='WH/IN/QA';state='assigned';write_date='pk1'
 def __init__(self,po,mode='done'):
  self.company_id=po.company_id;self.picking_type_id=N(code='incoming',create_backorder='ask');self.location_id=N(usage='supplier')
  self.move_ids=Records([Move(po,1),Move(po,2,3)]);self.mode=mode;self.validations=0
 def button_validate(self):
  self.validations+=1
  if self.mode=='wizard':return {'res_model':'stock.backorder.confirmation','context':{'button_validate_picking_ids':[5]}}
  if self.mode=='blocked':return {'res_model':'stock.immediate.transfer'}
  self.state='done';return True
class Wizard:
 def __init__(self,p):self.p=p;self.created=0
 def sudo(self):return self
 def with_company(self,c):return self
 def with_context(self,**ctx):self.context=ctx;return self
 def create(self,v):assert v=={'pick_ids':[(6,0,[5])]};self.created+=1;return self
 def process(self):self.p.state='done';return True
ctx={'json':json,'math':math,'_':lambda s:s,'UserError':UserError,'ValidationError':ValidationError,
 'float_compare':lambda a,b,precision_rounding:0 if abs(a-b)<precision_rounding/2 else (1 if a>b else -1)}
tree=ast.parse((R/'models/portal_receipt.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef));cls.bases=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls],type_ignores=[])),'receipt helpers','exec'),ctx)
Model=ctx['PurchaseOrderReceipt']
class PO(Model):
 id=10;state='purchase';company_id=object()
 def __init__(self,mode='done'):
  self.user=N(has_group=lambda g:False);self.absar_portal_preparer_id=self.user;self.p=Picking(self,mode);self.picking_ids=Records([self.p]);self.wizard=Wizard(self.p)
  self.env=Env(self.wizard)
 def ensure_one(self):pass
 def _portal_actor(self,r):assert r=='preparer';return self.user
 def _portal_check_company(self,u):assert u==self.user
 def _portal_lock(self):pass
 def sudo(self):return self
 def invalidate_recordset(self):pass
class Env:
 def __init__(self,w):self.w=w;self.locks=[];self.cr=N(execute=lambda q,a:self.locks.append((q,a)))
 def __getitem__(self,k):assert k=='stock.backorder.confirmation';return self.w

def payload(po,quantities=(5,3)):
 return [dict(id=m.id,quantity=q) for m,q in zip(po.p.move_ids,quantities)]
def receive(po,rows=None,version=None):return po._portal_receive(5,version or po._portal_receipt_version(po.p),rows if rows is not None else payload(po))
def deny(fn,exc=(UserError,ValidationError,AccessError)):
 try:fn()
 except exc:return
 raise AssertionError('Expected rejection')
po=PO();rows=po._portal_receipts();assert rows[0]['lines'][0]['expected']==5
assert receive(po)['state']=='done' and po.p.validations==1
assert [m.quantity for m in po.p.move_ids]==[5,3]
deny(lambda:receive(po));assert po.p.validations==1
po=PO('wizard');assert receive(po,payload(po,(2,0)))['state']=='done';assert po.wizard.created==1
assert po.wizard.context['button_validate_picking_ids']==[5]
assert [m.quantity for m in po.p.move_ids]==[2,0] and not po.p.move_ids[1].picked
for values in [(0,0),(-1,0),(6,0),(float('nan'),0),(float('inf'),0),(True,0)]:
 po=PO();deny(lambda:receive(po,payload(po,values)));assert po.p.validations==0
po=PO();deny(lambda:receive(po,version='stale'));assert po.p.validations==0
po=PO();deny(lambda:receive(po,[{'id':1,'quantity':1},{'id':1,'quantity':2}]))
po=PO();deny(lambda:receive(po,[{'id':999,'quantity':1},{'id':2,'quantity':2}]))
po=PO();deny(lambda:po._portal_receive(999,'version',payload(po)))
po=PO();po.p.move_ids[0].purchase_line_id.order_id=object();deny(lambda:receive(po));assert po.p.validations==0
po=PO();po.p.location_id.usage='internal';deny(lambda:receive(po))
po=PO();po.p.company_id=object();deny(lambda:receive(po))
po=PO();po.state='draft';deny(lambda:receive(po))
po=PO();po.absar_portal_preparer_id=object();deny(lambda:receive(po))
po=PO();po._portal_actor=lambda r:(_ for _ in ()).throw(AccessError('role'));deny(lambda:receive(po))
po=PO();po.p.move_ids[0].product_id.tracking='serial';deny(lambda:receive(po));assert po.p.validations==0
po=PO();po.p.picking_type_id.create_backorder='never';deny(lambda:receive(po,payload(po,(2,0))))
po=PO('blocked');deny(lambda:receive(po));assert po.p.state!='done'
print('PASS: native validation invoked; full/partial inputs; native backorder wizard; zeroed unselected lines; company/ownership/role/state checks; stale/duplicate/foreign/invalid quantities; over-receipt and tracked-product guards; repeat validation blocked (isolated recordset fixtures, no ORM).')
