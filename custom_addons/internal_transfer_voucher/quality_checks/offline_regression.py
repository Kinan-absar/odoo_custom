"""Offline regression harness: executes module methods with lightweight ORM doubles.
It is deliberately not an Odoo staging/integration test.
"""
import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path

class UserError(Exception): pass
class Base:
    def ensure_one(self): return self
class Api:
    def model(self,f): return f
    def model_create_multi(self,f): return f
    def depends(self,*a): return lambda f:f
    def onchange(self,*a): return lambda f:f
class DateField:
    def __call__(self,*a,**kw): return None
    def context_today(self,*a): return date(2026,10,7)
class Fields:
    Date=DateField()
    Datetime=types.SimpleNamespace(now=datetime.now)
    def __getattr__(self,k): return lambda *a,**kw:None
odoo=types.ModuleType('odoo');odoo.api=Api();odoo.fields=Fields();odoo.models=types.SimpleNamespace(Model=Base);odoo._=lambda x:x
odoo.fields.Datetime=type('DT',(),{'__new__':lambda cls,*a,**kw:None,'now':staticmethod(datetime.now)})
sys.modules['odoo']=odoo
exceptions=types.ModuleType('odoo.exceptions');exceptions.UserError=UserError;sys.modules['odoo.exceptions']=exceptions
spec=importlib.util.spec_from_file_location('fixed_agent',Path(__file__).resolve().parents[1] / 'models' / 'payment_review_agent.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Row:
    def __init__(self,**kw): self.__dict__.update(kw)
    def __getattr__(self,k): return False
    def with_context(self,**kw): return self
    def write(self,vals):
        for k,v in vals.items():
            if isinstance(v,list) and v and isinstance(v[0],tuple):
                if v[0][0]==5: v=RS()
                elif v[0][0]==6: v=RS([Row(id=i) for i in v[0][2]])
            setattr(self,k,v)
    def action_cancel(self): self.state='cancel'
    @property
    def ids(self): return [self.id]

class RS:
    def __init__(self,items=()): self.items=list(items)
    def __iter__(self):return iter(self.items)
    def __len__(self):return len(self.items)
    def __bool__(self):return bool(self.items)
    def __getitem__(self,k):return RS(self.items[k]) if isinstance(k,slice) else self.items[k]
    def __contains__(self,x):return x in self.items
    def __sub__(self,other):return RS([x for x in self if x not in (list(other) if isinstance(other,RS) else [other])])
    def __or__(self,other):
        out=list(self.items)
        for x in list(other) if isinstance(other,RS) else [other]:
            if x not in out:out.append(x)
        return RS(out)
    def __getattr__(self,k):
        if not self.items:return RS() if k.endswith('_ids') or k.endswith('_id') else False
        return getattr(self.items[0],k)
    def __eq__(self,other):return self.items==other.items if isinstance(other,RS) else len(self.items)==1 and self.items[0] is other
    @property
    def ids(self):return [x.id for x in self]
    def filtered(self,f):return RS([x for x in self if f(x)])
    def sorted(self,key):return RS(sorted(self.items,key=key))
    def mapped(self,path):
        vals=[]
        for x in self:
            for part in path.split('.'):x=getattr(x,part)
            vals.extend(list(x) if isinstance(x,RS) else [x])
        return RS(vals) if (vals and isinstance(vals[0],Row)) or path.split('.')[-1].endswith(('_ids','_id')) else vals
    def with_context(self,**kw):return self
    def write(self,vals):
        for x in self:x.write(vals)
    def action_cancel(self):
        for x in self:x.action_cancel()

class Currency(Row):
    def is_zero(self,v):return abs(v)<.005
    def compare_amounts(self,a,b):return 0 if self.is_zero(a-b) else (1 if a>b else -1)
    def _convert(self,a,target,company,ondate):return a*self.rate/target.rate

class Store:
    def __init__(self):self.rows=[]
    def search(self,domain,**kw):
        rows=self.rows
        for field,op,value in domain:
            if field=='state':rows=[r for r in rows if (r.state not in value if op=='not in' else r.state in value)]
            elif field=='purchase_order_ids':rows=[r for r in rows if value in r.purchase_order_ids.ids]
        return RS(rows[:kw.get('limit')] if kw.get('limit') else rows)
    def create(self,vals):
        r=Row(id=100+len(self.rows),state='planned',ceo_decision='not_sent',is_unplanned=False,purchase_order_ids=RS(),**{k:v for k,v in vals.items() if k!='purchase_order_ids'})
        if 'purchase_order_ids' in vals:r.purchase_order_ids=RS([Row(id=i) for i in vals['purchase_order_ids'][0][2]])
        self.rows.append(r);return r

def domain_match(row,domain):
    def value(path):
        obj=row
        for field in path.split('.'):obj=getattr(obj,field)
        return obj
    def atom(term):
        field,op,want=term;actual=value(field)
        if isinstance(actual,Row):actual=actual.id
        if isinstance(actual,datetime) and isinstance(want,date):actual=actual.date()
        if op=='=':return actual==want
        if op=='!=':return actual!=want
        if op=='in':return actual in want
        if op=='not in':return actual not in want
        if not actual:return False
        return {'>=':lambda:actual>=want,'<=':lambda:actual<=want,'<':lambda:actual<want}[op]()
    terms=iter(domain)
    def consume(term):
        if term in ('|','&'):
            a=consume(next(terms));b=consume(next(terms));return a or b if term=='|' else a and b
        return atom(term)
    return all([consume(term) for term in terms])

class ModelSet(RS):
    def __init__(self,rows):super().__init__();self.rows=rows
    def search(self,domain,**kw):return RS([r for r in self.rows if domain_match(r,domain)])

class Collector:
    def create(self,vals):self.values=vals

class ActionSet(RS):
    def write(self,vals):
        for row in self:
            for key,value in vals.items():setattr(row,key,value)

class Agent(module.CashPlanLinePaymentAgent):
    def __bool__(self):return False
    def __iter__(self):return iter(())
    def __or__(self,other):return RS()|other
    def __getitem__(self,key):return RS()[key]
    def filtered(self,f):return RS()
    def mapped(self,path):return RS().mapped(path)
    def _agent_get_payable_data(self,c):return {self.partner.id:dict(net_due=self.due,bills=self.bills,oldest_due=False,aging_summary='test')}
    def _agent_get_retention_data(self,c):return {self.partner.id:{'net_due':self.retention_open}}
    def _agent_retention_controls(self,c):return self.controls
    def _agent_signature_note(self,po):return 'Unsigned' if po.signature_state=='pending' else False
    def _agent_po_draft_bills(self,po):return RS()
    def _agent_po_due_company_currency(self,po,c):return po.amount_paid_residual

class Rec(module.CashPlanReviewLine):
    def __setattr__(self,k,v):
        if k=='bill_ids' and isinstance(v,list) and v and isinstance(v[0],tuple):
            v=RS([Row(id=i) for i in v[0][2]])
        object.__setattr__(self,k,v)
    def _suggest_category(self,p):return Row(id=10)
    def _active_supplier_plans(self):return RS([r for r in self.store.rows if r.state not in ('cancel','executed')])

class Tests(unittest.TestCase):
    def setUp(self):
        self.currency=Currency(id=1,rate=1,rounding=.01)
        self.company=Row(id=1,currency_id=self.currency)
        self.partner=Row(id=1,display_name='Supplier');self.partner.commercial_partner_id=self.partner
        self.po=Row(id=7,name='PO7',company_id=self.company,partner_id=self.partner,state='purchase',invoice_status='no',signature_state='signed',amount_paid_residual=100,amount_untaxed=100,currency_id=self.currency,date_order=datetime(2026,1,1),invoice_ids=RS())
        self.agent=Agent();self.agent.partner=self.partner;self.agent.due=8;self.agent.bills=RS();self.agent.retention_open=5
        self.store=Store();self.agent.search=self.store.search;self.agent.create=self.store.create
        self.env={'cash.plan.line':self.agent,'res.partner':Row(browse=lambda pid:self.partner),'account.move':RS(),'account.account':Row(search=lambda *a,**kw:Row(id=19))}
        self.env=type('Env',(dict,),{})(self.env);self.env.cr=Row(execute=lambda *a:None)
        self.agent.env=self.env
        self.rec=Rec();self.rec.env=self.env;self.rec.store=self.store;self.rec.review_id=Row(company_id=self.company);self.rec.partner_id=self.partner;self.rec.purchase_order_id=RS();self.rec.plan_line_id=RS();self.rec.target_plan_line_id=RS();self.rec.source_type='new_payable';self.rec.action='add';self.rec.agent_action='add';self.rec.proposed_amount=8;self.rec.amount_confirmed=False;self.rec.applied=False;self.rec.can_apply=False;self.rec.bill_ids=RS()
        self.agent.controls={'po_data':{},'generated_by_partner':{1:5},'po_count_by_partner':{1:1},'ambiguous_partners':set(),'retention_data':{1:{'net_due':5}}}
    def plan(self,po=False,amount=7,decision='pending',name='Balance'):
        r=Row(id=len(self.store.rows)+1,name=name,description='',category_id=False,account_id=False,company_id=self.company,partner_id=self.partner,forecast_amount=amount,purchase_order_ids=RS([self.po]) if po else RS(),ceo_decision=decision,state='planned',is_unplanned=False,flow_type='out',transaction_type='supplier')
        self.store.rows.append(r);return r
    def bill(self,subtotal=100,retention=5,refund=False,currency=None):
        product=Row(display_type='product',purchase_line_id=Row(order_id=self.po),account_id=Row(code='601001'),price_subtotal=subtotal,balance=(-1 if refund else 1)*subtotal)
        ret=Row(display_type='product',purchase_line_id=False,account_id=Row(code='201019'),price_subtotal=-retention,balance=(1 if refund else -1)*retention)
        move=Row(id=8,state='posted',move_type='in_refund' if refund else 'in_invoice',currency_id=currency or self.currency,invoice_date=date(2026,1,1),date=date(2026,1,1),invoice_line_ids=RS([product,ret]),line_ids=RS([product,ret]))
        self.po.invoice_ids=self.po.invoice_ids|move;return move
    def test_stored_false_does_not_skip_payable_add(self):
        self.rec._apply_recommendation();self.assertTrue(self.rec.applied);self.assertEqual(self.store.rows[0].forecast_amount,8)
    def test_pending_update_resets_ceo(self):
        line=self.plan();self.rec.plan_line_id=line;self.rec.source_type='existing_payable';self.rec.action='update';self.rec._apply_recommendation();self.assertEqual((line.forecast_amount,line.ceo_decision),(8,'not_sent'))
    def test_remove_duplicate(self):
        self.plan(amount=8);line=self.plan();self.rec.plan_line_id=line;self.rec.source_type='existing_payable';self.rec.action=self.rec.agent_action='remove';self.rec._apply_recommendation();self.assertEqual(line.state,'cancel')
    def test_remove_positive_only_plan_rejected(self):
        line=self.plan();self.rec.plan_line_id=line;self.rec.source_type='existing_payable';self.rec.action=self.rec.agent_action='remove'
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_approved_update_rejected(self):
        self.rec.plan_line_id=self.plan(decision='approved');self.rec.action='update';self.assertFalse(self.rec._decision_is_safely_applicable())
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_held_rejected_pending_eligibility(self):
        for state in ['held','rejected','pending','not_sent']:
            l=self.plan(decision=state);self.assertTrue(self.agent._agent_safe_to_change(l));self.assertTrue(self.rec._safe_line(l))
    def test_stale_amount_rejected(self):
        self.agent.due=9
        with self.assertRaises(UserError):self.rec._apply_recommendation()
        self.assertFalse(self.store.rows)
    def test_duplicate_add_rejected(self):
        self.plan(amount=8)
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_new_po_requires_confirmation(self):
        self.rec.source_type='new_po';self.rec.purchase_order_id=self.po;self.assertFalse(self.rec._decision_is_safely_applicable())
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_confirmed_po_add(self):
        self.rec.source_type='new_po';self.rec.purchase_order_id=self.po;self.rec.amount_confirmed=True;self.rec._apply_recommendation();self.assertEqual(self.store.rows[0].purchase_order_ids.ids,[7])
    def test_unsigned_po_blocked(self):
        self.rec.source_type='new_po';self.rec.purchase_order_id=self.po;self.rec.amount_confirmed=True;self.po.signature_state='pending';self.assertFalse(self.rec._decision_is_safely_applicable())
    def test_excess_po_amount_rejected(self):
        self.rec.source_type='new_po';self.rec.purchase_order_id=self.po;self.rec.amount_confirmed=True;self.rec.proposed_amount=101
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_convert_clears_po(self):
        self.bill();line=self.plan(po=True);self.rec.action='convert';self.rec.source_type='existing_po';self.rec.plan_line_id=line;self.rec.purchase_order_id=self.po;self.rec._apply_recommendation();self.assertFalse(line.purchase_order_ids);self.assertEqual(line.name,'Balance Due - Supplier')
    def test_second_conversion_reuses_live_target(self):
        self.bill();a=self.plan(po=True);self.rec.action='convert';self.rec.source_type='existing_po';self.rec.plan_line_id=a;self.rec.purchase_order_id=self.po;self.rec._apply_recommendation()
        b=self.plan(po=True);self.rec.applied=False;self.rec.plan_line_id=b;self.rec.target_plan_line_id=RS();self.rec._apply_recommendation();self.assertEqual(b.state,'cancel');self.assertEqual(a.forecast_amount,8);self.assertFalse(a.purchase_order_ids)
    def test_partial_po_convert_blocked(self):
        self.bill(subtotal=50);self.rec.action='convert';self.rec.source_type='existing_po';self.rec.plan_line_id=self.plan(po=True);self.rec.purchase_order_id=self.po
        with self.assertRaises(UserError):self.rec._apply_recommendation()
    def test_retention_product_lines(self):
        self.bill();d=self.agent._agent_po_retention_candidate_data(self.po,self.company);self.assertEqual((d['gross_invoiced'],d['retention_generated']),(100,5));self.assertTrue(d['fully_invoiced_by_amount'])
    def test_refund_reduces_completion_and_retention(self):
        self.bill();self.bill(subtotal=10,retention=1,refund=True);d=self.agent._agent_po_retention_candidate_data(self.po,self.company);self.assertEqual((d['gross_invoiced'],d['retention_generated']),(90,4));self.assertFalse(d['fully_invoiced_by_amount'])
    def test_foreign_currency_completion(self):
        foreign=Currency(rate=3.75,rounding=.01);self.po.currency_id=foreign;move=self.bill(currency=foreign);move.invoice_line_ids[0].balance=375;move.invoice_line_ids[1].balance=-18.75
        d=self.agent._agent_po_retention_candidate_data(self.po,self.company);self.assertTrue(d['fully_invoiced_by_amount']);self.assertEqual(d['gross_invoiced'],375)
    def test_two_po_release_ambiguous(self):
        self.agent.controls['generated_by_partner'][1]=10;self.agent.controls['po_count_by_partner'][1]=2
        clear,amt=self.agent._agent_retention_allocation(self.po,{'retention_generated':5,'allocation_clear':True},self.agent.controls,self.company);self.assertFalse(clear)
    def test_two_po_full_balance_each_entitlement(self):
        self.agent.controls['generated_by_partner'][1]=10;self.agent.controls['po_count_by_partner'][1]=2;self.agent.controls['retention_data'][1]['net_due']=10
        self.assertEqual(self.agent._agent_retention_allocation(self.po,{'retention_generated':5,'allocation_clear':True},self.agent.controls,self.company),(True,5))
    def test_single_po_partial_release(self):
        self.agent.controls['retention_data'][1]['net_due']=3
        self.assertEqual(self.agent._agent_retention_allocation(self.po,{'retention_generated':5,'allocation_clear':True},self.agent.controls,self.company),(True,3))
    def test_zero_balance_can_remove_multi_po_retention(self):
        self.agent.controls['generated_by_partner'][1]=10;self.agent.controls['po_count_by_partner'][1]=2;self.agent.controls['retention_data'][1]['net_due']=0
        self.assertEqual(self.agent._agent_retention_allocation(self.po,{'retention_generated':5,'allocation_clear':True},self.agent.controls,self.company),(True,0))
    def test_add_retention(self):
        self.bill();data=self.agent._agent_po_retention_candidate_data(self.po,self.company);self.agent.controls['po_data'][7]=data;self.rec.source_type='new_retention';self.rec.purchase_order_id=self.po;self.rec.proposed_amount=5;self.rec._apply_recommendation();self.assertEqual(self.store.rows[0].account_id,19);self.assertEqual(self.store.rows[0].forecast_amount,5)
    def test_retention_account_exact(self):
        self.assertTrue(self.agent._agent_is_retention_account(Row(code='201019')));self.assertFalse(self.agent._agent_is_retention_account(Row(code='999999',name='Retention other')))
    def populate(self,year='2026'):
        collector=Collector();self.env['cash.plan.review.line']=collector;self.env['purchase.order']=ModelSet([self.po])
        self.agent.search=lambda domain,**kw:RS([r for r in self.store.rows if domain_match(r,domain)])
        self.bill();self.agent.controls['po_data'][7]=self.agent._agent_po_retention_candidate_data(self.po,self.company)
        self.agent._populate_payment_review(Row(id=1,year=year,company_id=self.company))
        return collector.values
    def test_year_includes_undated_update(self):
        line=self.plan();vals=self.populate();self.assertTrue(any(v.get('plan_line_id')==line.id and v['action']=='update' for v in vals));self.assertFalse(any(v['source_type']=='new_payable' and v['action']=='add' for v in vals))
    def test_year_does_not_duplicate_prior_year_plan(self):
        line=self.plan(amount=8);line.planned_date=date(2025,1,1);vals=self.populate();self.assertFalse(any(v['source_type']=='new_payable' and v['action']=='add' for v in vals))
    def test_generator_add_retention(self):
        vals=self.populate();self.assertTrue(any(v['source_type']=='new_retention' and v['action']=='add' and v['proposed_amount']==5 for v in vals))
    def test_generator_update_existing_retention(self):
        line=self.plan(po=True,amount=5.05,name='Retention');line.account_id=Row(code='201019',name='Retention Payable');vals=self.populate();self.assertTrue(any(v.get('plan_line_id')==line.id and v['source_type']=='existing_retention' and v['action']=='update' and v['proposed_amount']==5 for v in vals))
    def test_generator_multi_po_blocks_payable_add(self):
        line=self.plan(po=True);line.purchase_order_ids=line.purchase_order_ids|Row(id=9);vals=self.populate();self.assertFalse(any(v['source_type']=='new_payable' and v['action']=='add' for v in vals));self.assertTrue(any(v['source_type']=='new_payable' and v['action']=='review' for v in vals))
    def test_duplicate_retention_plans_remain_manual(self):
        for amount in [2,3]:
            line=self.plan(po=True,amount=amount,name='Retention');line.account_id=Row(code='201019')
        vals=self.populate();ret=[v for v in vals if v['source_type']=='existing_retention'];self.assertEqual(len(ret),2);self.assertTrue(all(v['action']=='review' for v in ret))
    def test_native_selection_empty_reports_error(self):
        with self.assertRaisesRegex(UserError,'Select at least one'):
            module.CashPlanReviewLine.action_apply_selected_from_list(ActionSet())
    def test_native_selection_unsafe_reports_error(self):
        self.rec.action='review';self.rec._fields={'action':Row(selection=[('review','Review')])}
        with self.assertRaisesRegex(UserError,'No selected changes were applied'):
            module.CashPlanReviewLine.action_apply_selected_from_list(ActionSet([self.rec]))
        self.assertFalse(self.store.rows)
    def test_native_selection_success_reports_and_preserves_scope(self):
        self.rec.review_id.line_ids=RS([self.rec]);self.rec.review_id.action_open_recommendations=lambda:{'domain':[('review_id','=',44)]}
        result=module.CashPlanReviewLine.action_apply_selected_from_list(ActionSet([self.rec]))
        self.assertTrue(self.rec.applied);self.assertEqual(result['params']['type'],'success');self.assertEqual(result['params']['next']['domain'],[('review_id','=',44)])

if __name__=='__main__':unittest.main(verbosity=2)
