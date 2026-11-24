"""Execute real report/visibility guards without an Odoo server."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from copy import deepcopy
from lxml import etree
class UserError(Exception):pass
class Base:
    def _get_view(self,**kw):return etree.fromstring(b'<form><header><button name="7" type="action" string="Arabic label"/><button name="x" string="Print PI" invisible="state == \'cancel\'"/><button name="other" string="Save"/></header></form>'),NS()
    def _render_qweb_pdf(self,*a,**kw):return 'pdf'
    def _render_qweb_html(self,*a,**kw):return 'html'
source=ast.parse((Path(__file__).resolve().parents[1]/'models/report_approval.py').read_text())
classes=[]
for c in source.body:
    if not isinstance(c,ast.ClassDef):continue
    c.bases=[ast.Name(id='Base',ctx=ast.Load())]
    c.body=[n for n in c.body if isinstance(n,ast.FunctionDef)]
    for n in c.body:n.decorator_list=[]
    classes.append(c)
scope={'Base':Base,'UserError':UserError,'_':lambda s:s,'deepcopy':deepcopy,'etree':etree}
exec(compile(ast.fix_missing_locations(ast.Module(body=classes,type_ignores=[])),'report_approval.py','exec'),scope)
Sale=scope['SaleOrderPrintApproval'];Report=scope['SalesReportApproval']
user=NS(sudo=lambda *a:user)
class Env:
    user=user;context={}
    def __getitem__(self,model):
        if model=='ir.actions.report':return NS(sudo=lambda:NS(search=lambda d:NS(ids=[7])))
        return NS(browse=lambda ids:NS(exists=lambda:orders))
class Orders(Sale,list):pass
orders=Orders();orders.env=Env()
for required,state,approver,allowed in [(True,'draft',False,False),(True,'submitted',False,False),(True,'returned',False,False),(True,'approved',False,False),(True,'approved',True,True),(False,'draft',False,True)]:
    row=NS(_absar_review_permissions=lambda user,r=required:{'requires_review':r},absar_portal_review_state=state,absar_portal_approver_id=approver)
    orders[:]=[row];orders._compute_absar_can_print();assert row.absar_can_print==allowed
    report=Report();report.env=Env();report._get_report=lambda ref:NS(model='sale.order')
    for method in ('_render_qweb_pdf','_render_qweb_html'):
        try:result=getattr(report,method)('custom.quotation',[1]);assert allowed
        except UserError:assert not allowed
orders[:]=[NS(absar_can_print=True),NS(absar_can_print=False)]
try:orders._absar_assert_print_approved();raise AssertionError('Mixed batch bypassed approval')
except UserError:pass
arch,_=orders._get_view();assert arch.xpath('//field[@name="absar_can_print"]')
for name in ('7','x'):assert 'not absar_can_print' in arch.xpath('//button[@name="%s"]'%name)[0].get('invisible')
assert arch.xpath('//button[@name="other"]')[0].get('invisible') is None
report._get_report=lambda ref:NS(model='account.move');assert report._render_qweb_pdf('other',[1])=='pdf'
print('PASS: backend/custom PDF and HTML/PI guards block draft/submitted/returned/forged/mixed cases; approved and uncontrolled documents pass; custom numeric/translated report buttons hide; unrelated reports unchanged.')
