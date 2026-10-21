"""Exercise actual workflow methods with record/transaction-shaped fixtures (no Odoo server)."""
import ast
from pathlib import Path
from types import SimpleNamespace as N

class AccessError(Exception):pass
class UserError(Exception):pass
class ValidationError(Exception):pass
class User:
    def __init__(self,uid,*roles,share=False):
        self.id=uid;self.name='User %s'%uid;self.active=True;self.share=share
        self.roles=set(roles);self.company_id=7;self.company_ids=[7];self.employee_id=True
    def has_group(self,name):return name.rsplit('group_portal_sales_',1)[-1] in self.roles
    def sudo(self,*args):return self
    def with_company(self,*args):return self
    def __bool__(self):return bool(self.id)
    def __or__(self,other):return Users([self])|other
class Users(list):
    def __or__(self,other):
        rows=other if isinstance(other,Users) else [other]
        return Users(dict.fromkeys([u for u in list(self)+list(rows) if u]))
    def filtered(self,fn):return Users(u for u in self if fn(u))
class Lines(list):
    def filtered(self,fn):return Lines(l for l in self if fn(l))

class Base:
    def __getattr__(self,key):
        if key in self._data:return self._data[key]
        raise AttributeError(key)
    def __setattr__(self,key,value):
        if key.startswith('_') or key=='env':object.__setattr__(self,key,value)
        else:self._data[key]=value
    def __iter__(self):return iter([self])
    def ensure_one(self):pass
    def filtered(self,name):return [self] if getattr(self,name) else []
    def sorted(self,name):return [self]
    def sudo(self,*args):return self
    def with_company(self,*args):return self
    def with_context(self,**kw):
        clone=object.__new__(type(self));clone._data=self._data
        clone.env=N(user=self.env.user,uid=self.env.uid,context=dict(self.env.context,**kw))
        return clone
    def write(self,vals):
        self._data.update({key:(user_map.get(value,empty) if key.endswith('_id') and key.startswith('absar_') else value) for key,value in vals.items()});return True
    def create(self,vals):return vals
    def action_confirm(self):
        if self._data.get('native_failure'):raise UserError('Native confirmation validation')
        self.write({'state':'sale'});return True
    def action_draft(self):self.write({'state':'draft'});return True

root=Path(__file__).parents[1]
tree=ast.parse((root/'models/sale_order.py').read_text())
klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SaleOrder')
klass.bases=[ast.Name(id='Base',ctx=ast.Load())]
klass.body=[n for n in klass.body if isinstance(n,ast.FunctionDef)]
for fn in klass.body:fn.decorator_list=[]
ns=dict(Base=Base,_=lambda s:s,AccessError=AccessError,UserError=UserError,ValidationError=ValidationError,
        fields=N(Datetime=N(now=lambda:'2026-10-21 15:00:00')),_PREFIX='absar_portal_sales.',_REVIEW_TOKEN=object(),float_compare=lambda a,b,precision_digits:round(a-b,precision_digits))
ns['_REVIEW_FIELDS']={'absar_portal_creator_id','absar_portal_submitter_id','absar_portal_review_state','absar_portal_approver_id',
                     'absar_order_review_state','absar_order_requester_id','absar_order_approver_id'}
exec(compile(ast.fix_missing_locations(ast.Module(body=[klass],type_ignores=[])),'actual sales review','exec'),ns)
Sale=ns['SaleOrder'];empty=User(0);preparer=User(1,'creator');approver=User(2,'creator','approver');operator=User(3,'creator','user');other=User(4,'creator');outsider=User(5)
user_map={u.id:u for u in (empty,preparer,approver,operator,other,outsider)}

def order(actor=preparer,**changes):
    obj=Sale();obj._data=dict(id=10,name='S00506',company_id=7,state='draft',absar_portal_creator_id=preparer,
        absar_portal_submitter_id=preparer,absar_portal_approver_id=empty,absar_portal_review_state='draft',
        absar_order_review_state='none',absar_order_requester_id=empty,absar_order_approver_id=empty,
        absar_portal_review_note='',absar_proposal_type='standard',absar_proposal_payment_ids=[],
        order_line=Lines([N(display_type=False,product_uom_qty=1)]),events=[])
    obj._data.update(changes);obj.env=N(user=actor,uid=actor.id,context={})
    obj._absar_portal_lock=lambda:obj.events.append('lock')
    obj._absar_native_review_access=lambda:obj.events.append('access')
    obj._absar_portal_notify_reviewers=lambda conversion=False:obj.events.append(('reviewers',conversion))
    obj._absar_portal_notify_creator=lambda message:obj.events.append(('creator',message))
    obj._absar_portal_close_activities=lambda:obj.events.append('close')
    return obj

def reject(call,exc=UserError):
    try:call()
    except exc:return
    raise AssertionError('Expected '+exc.__name__)

# Two stages for both account types; author, submitter, requester cannot approve themselves.
for share in (False,True):
    preparer.share=share;approver.share=share
    o=order();o._absar_portal_submit();assert o.absar_portal_review_state=='submitted'
    reject(o._absar_portal_submit);assert o.events.count(('reviewers',False))==1
    reject(o.action_confirm)
    o.env.user=approver;o.action_absar_portal_approve()
    assert o.state=='draft' and o.absar_portal_review_state=='approved'
    assert 'Request Sales Order approval' in o.events[-1][1]
    reject(o.action_absar_portal_approve);reject(o.action_confirm)
    o.env.user=preparer;o.action_absar_request_order();assert o.absar_order_review_state=='requested'
    reject(o.action_absar_request_order);reject(o.action_absar_approve_order,AccessError)
    o.env.user=approver;o.action_absar_approve_order()
    assert o.state=='sale' and o.absar_order_review_state=='approved' and o.absar_order_approver_id==approver
    assert 'now a Sales Order' in o.events[-1][1]
    reject(o.action_absar_approve_order)
preparer.share=False;approver.share=False
# Permissions and server actions exclude unauthorized requests and all self approvals.
o=order(absar_portal_review_state='approved',absar_portal_approver_id=approver)
assert o._absar_review_permissions(preparer)['can_request_order']
assert not o._absar_review_permissions(other)['can_request_order']
assert o._absar_review_permissions(operator)['can_request_order']
assert not o._absar_review_permissions(outsider)['can_request_order']
o.env.user=other;reject(o.action_absar_request_order)
o.env.user=approver;o.absar_portal_submitter_id=approver;o.absar_portal_review_state='submitted';reject(o.action_absar_portal_approve)
o=order(approver,absar_portal_review_state='approved',absar_portal_approver_id=approver,
        absar_order_review_state='requested',absar_order_requester_id=approver)
reject(o.action_absar_approve_order)
# Return conversion keeps the quotation approval and allows the preparer to re-request.
o=order(approver,absar_portal_review_state='approved',absar_portal_approver_id=approver,
        absar_order_review_state='requested',absar_order_requester_id=preparer)
reject(o.action_absar_return_order,ValidationError)
o.absar_portal_review_note='Customer signature required';o.action_absar_return_order()
assert o.absar_portal_review_state=='approved' and o.absar_order_review_state=='returned' and o.state=='draft'
o.env.user=preparer;o.action_absar_request_order();assert o.absar_order_review_state=='requested'
# Native validation failure never records a decision or sends an outcome.
o=order(approver,absar_portal_review_state='approved',absar_portal_approver_id=approver,
        absar_order_review_state='requested',absar_order_requester_id=preparer,native_failure=True)
reject(o.action_absar_approve_order)
assert o.absar_order_review_state=='requested' and not any(isinstance(e,tuple) and e[0]=='creator' for e in o.events)
# Content changes cancel both approvals; direct RPC metadata/state/create bypasses fail.
o.native_failure=False;o.write({'note':'Edited scope'})
assert o.absar_portal_review_state=='returned' and o.absar_order_review_state=='none'
reject(lambda:o.write({'state':'sale'}),AccessError)
reject(lambda:o.write({'absar_order_review_state':'approved'}),AccessError)
reject(lambda:o.create([{'state':'sale'}]),AccessError)
reject(lambda:o.create([{'absar_order_review_state':'approved'}]),AccessError)
# Unmanaged native orders retain the native workflow for non-preparers.
o=order(outsider,absar_portal_creator_id=empty);o.action_confirm();assert o.state=='sale'
# Outcome targets explicitly include original preparer, submitter, and conversion requester.
o=order(absar_portal_submitter_id=operator,absar_order_requester_id=other)
del o.__dict__['_absar_portal_notify_creator'];delivered=[]
o._absar_portal_notify=lambda users,title,message:delivered.extend(u.id for u in users)
o._absar_portal_notify_creator('Approved')
assert delivered==[1,3,4]
# Both native Confirm variants are hidden, and decisions precede the form details.
from lxml import etree
xml=etree.parse(str(root/'views/sale_order_views.xml'))
assert len(xml.xpath('//xpath[contains(@expr,"action_confirm")]/attribute'))==2
portal=etree.parse(str(root/'views/portal_sales_templates.xml'))
assert not portal.xpath('//button[contains(text(),"Confirm Sales Order") or contains(text(),"Approve for Sending")]')
detail=portal.xpath('//template[@id="sales_detail"]')[0]
assert detail.xpath('.//div[contains(@class,"aps-sales-actions")]')
assert not portal.xpath('//h3[text()="Create an offer"]')
print('PASS: actual two-stage workflow, native/portal actors, independent review, duplicate decisions, no direct Confirm/state/metadata/create bypass, native failure, return/re-request, content invalidation, three outcome recipients, both native Confirm variants and top portal actions (isolated fixtures).')
# Portal bell attention is persistent, including preparers with push disabled.
notices=ast.parse((root/'models/portal_notifications.py').read_text())
notice_class=next(n for n in notices.body if isinstance(n,ast.ClassDef))
notice_class.bases=[ast.Name(id='Base',ctx=ast.Load())]
notice_class.body=[n for n in notice_class.body if isinstance(n,ast.FunctionDef)]
for fn in notice_class.body:fn.decorator_list=[]
ns.update(PREFIX='absar_portal_sales.',expression=N(AND=lambda domains:[term for domain in domains for term in domain]))
exec(compile(ast.fix_missing_locations(ast.Module(body=[notice_class],type_ignores=[])),'actual portal notices','exec'),ns)
class Companies(list):
    @property
    def ids(self):return self
for u in user_map.values():u.company_ids=Companies([7])
def matches(domain,row):
    terms=iter(domain)
    def term(t):
        if t=='|':
            a=term(next(terms));b=term(next(terms));return a or b
        if t=='&':
            a=term(next(terms));b=term(next(terms));return a and b
        key,op,value=t;actual=row.get(key,False)
        if op=='=':return actual==value
        if op=='!=':return actual!=value
        if op=='in':return actual in value
        if op=='>':return bool(actual and actual>value)
        raise AssertionError(op)
    results=[term(t) for t in terms]
    return all(results)
def row():return dict(company_id=7,state='draft',absar_portal_creator_id=1,absar_portal_submitter_id=1,
    absar_order_requester_id=False,absar_portal_review_state='approved',absar_order_review_state='none',
    absar_sales_decision_at=False,write_date='2026-10-21 15:00:00')
# Avoid duplicate keyword defaults while constructing records.
def record(**kw):
    result=row();result.update(kw);return result
rows=[record(absar_sales_decision_at='2026-10-21 15:00:00'),
      record(absar_portal_creator_id=3,absar_sales_decision_at='2026-10-21 15:00:00'),
      record(absar_portal_creator_id=3,absar_portal_submitter_id=3,absar_order_requester_id=1,absar_sales_decision_at='2026-10-21 13:00:00'),
      record(company_id=99,absar_sales_decision_at='2026-10-21 15:00:00'),
      record(absar_portal_creator_id=3,absar_portal_submitter_id=3,absar_sales_decision_at='2026-10-21 15:00:00'),
      record(absar_portal_review_state='submitted'),record(absar_order_review_state='requested'),
      record(absar_portal_review_state='submitted',absar_portal_creator_id=2),
      record(absar_order_review_state='requested',absar_order_requester_id=2)]
notice=ns['SalesPortalNotifications']();notice._data={}
notice.env={'sale.order':N(sudo=lambda:N(search_count=lambda domain:sum(matches(domain,r) for r in rows)))}
notice._get_last_seen=lambda uid,kind:'2026-10-21 14:00:00'
summary=notice._get_sales_notification_summary(preparer)
assert summary['sales_review_update']['count']==3 and summary['sales_review_update']['new']==2
assert summary['sales_review_update']['url']=='/my/employee/sales/updates'
summary=notice._get_sales_notification_summary(approver)
assert summary['sales_approval']['count']==2 and summary['sales_approval']['new']==2
assert notice._get_sales_notification_summary(outsider)=={}
print('PASS: persistent portal notification summary: preparer/submitter/requester outcomes, both approval stages, seen timestamps, company isolation, self-review exclusion and role restrictions (query fixtures).')
