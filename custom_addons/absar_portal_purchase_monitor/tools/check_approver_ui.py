"""Exercise actual route guards and QWeb visibility expressions without Odoo."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'absar_portal_purchase_monitor.'
BASE = '/my/employee/purchase'
class Forbidden(Exception): pass
class ReachedDirectory(Exception): pass
class User:
    active = True
    share = True
    employee_id = True
    company_ids = NS(ids=[1])
    company_id = NS(id=1)
    id = 7
    def __init__(self, *roles): self.roles = roles
    def sudo(self): return self
    def with_company(self, company): return self
    def has_group(self, name):
        return any(name == PREFIX + 'group_portal_purchase_' + role for role in self.roles)
class Env:
    def __getitem__(self, name): raise ReachedDirectory(name)
request = NS(env=Env(), redirect=lambda url: url, httprequest=NS(path=BASE))
class MonitoringList:
    def _list_values(self, user, kw, **options):
        assert options['extra_domain'] == [('absar_portal_preparer_id', '=', user.id)]
        assert options['detail_base_url'] == BASE
        raise ReachedDirectory('monitoring list')
context = dict(PREFIX=PREFIX, BASE=BASE, Forbidden=Forbidden, request=request, PortalPurchaseMonitor=MonitoringList,
               expression=NS(AND=lambda groups: groups, OR=lambda groups: groups))

def extract(filename, name, methods, base=None):
    tree = ast.parse((ROOT/'controllers'/filename).read_text())
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    body = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    for method in body: method.decorator_list = []
    cls = ast.ClassDef(name=name, bases=[ast.Name(id=base, ctx=ast.Load())] if base else [],
                       keywords=[], body=body, decorator_list=[])
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), filename, 'exec'), context)
extract('portal_prepare.py', 'PortalPurchasePrepare', {'_actor', 'listing'})
extract('portal_directory.py', 'PortalPurchaseDirectory', {'orders', 'products'}, 'PortalPurchasePrepare')
service = context['PortalPurchaseDirectory']()
service._page = lambda *args, **kw: (_ for _ in ()).throw(ReachedDirectory('orders'))
service._company = lambda value: (_ for _ in ()).throw(ReachedDirectory('products'))
for roles in [('approver',), ('monitor',), ('preparer',), ('preparer', 'approver')]:
    request.env.user = User(*roles)
    try: service.products()
    except Forbidden: assert 'preparer' not in roles
    except ReachedDirectory: assert 'preparer' in roles
    else: raise AssertionError('Expected role guard or allowed product query')
    try: result = service.orders()
    except ReachedDirectory: assert 'preparer' in roles and 'monitor' not in roles
    else: assert result == ('/my/employee/purchase-monitor' if 'monitor' in roles else BASE+'/approvals')
request.env.user = User('approver')
request.httprequest.path = BASE+'/confirmations'
assert service.listing() == BASE+'/approvals'

workspace = etree.parse(str(ROOT/'views/portal_workspace_pages.xml'))
nav_condition = workspace.xpath('//template[@id="purchase_workspace_nav"]/header/@t-if')[0]
request.env.user = User('approver')
assert not eval(nav_condition, {'request':request})
request.env.user = User('preparer')
assert eval(nav_condition, {'request':request})
views = etree.parse(str(ROOT/'views/portal_purchase_prepare.xml'))
shared = etree.parse(str(ROOT/'views/portal_purchase_approval_list.xml'))
assert views.xpath('//template[@id="purchase_prepare_list"]/*[@t-call="absar_portal_purchase_monitor.purchase_approval_list"]')
assert shared.xpath('//div[@class="absar-record-list"]//article[@class="absar-record-card"][@t-att-data-record-href]')
for approval in (True, False):
    values = dict(approval=approval, confirmations=False, orders_only=False, request=request)
    nav = shared.xpath('//*[@t-call="absar_portal_purchase_monitor.purchase_workspace_nav"]')[0]
    assert bool(eval(nav.get('t-if'), values)) == (not approval)
    create = shared.xpath('//a[@href="/my/employee/purchase/new"]')[0]
    assert bool(eval(create.get('t-if'), values)) == (not approval)
heading = shared.xpath('//h2/@t-out')[0]
assert eval(heading, dict(approval=True)) == 'Purchase Approvals'
monitor = etree.parse(str(ROOT/'views/portal_purchase_templates.xml'))
assert monitor.xpath('//template[@id="purchase_monitor_list"]//article[@class="absar-record-card"]/@t-att-data-record-href') == ["'%s/%d' % (detail_base_url,r['po'].id)"]
detail = views.xpath('//template[@id="purchase_prepare_detail"]//*[@t-call="absar_portal_purchase_monitor.purchase_workspace_nav"]')[0]
assert not eval(detail.get('t-if'), {'boot': {'approval_view':True}})
assert eval(detail.get('t-if'), {'boot': {'approval_view':False}})
print('PASS: Approver/Issuer share monitoring list styling; existing PO form retained; Approver has one page, no app header or issuance action; legacy links redirect; Products require Issuer; Issuer and Monitor paths retained.')

# Monitor bookmarks open the shared form, with original company/state guards.
class NotFound(Exception): pass
context['NotFound'] = NotFound
extract('portal_purchase.py', 'PortalPurchaseMonitor', {'_user', 'order_detail'})
monitor_service = context['PortalPurchaseMonitor']()
company = NS(id=1)
user = User('monitor'); user.company_ids = [company]
po = NS(id=19, company_id=company, state='purchase')
po.exists = lambda: po
class OrderModel:
    def sudo(self): return self
    def browse(self, ident): assert ident == 19; return po
class MonitorEnv:
    def __init__(self): self.user = user
    def __getitem__(self, name): assert name == 'purchase.order'; return OrderModel()
request.env = MonitorEnv()
assert monitor_service.order_detail(19) == BASE+'/19?from_monitor=1'
for state, selected_company in [('draft', company), ('purchase', NS(id=2))]:
    po.state = state; po.company_id = selected_company
    try: monitor_service.order_detail(19)
    except NotFound: pass
    else: raise AssertionError('Monitor must not see draft or foreign-company orders')
request.env.user = User('approver')
try: monitor_service.order_detail(19)
except Forbidden: pass
else: raise AssertionError('Approver role alone must not grant Monitor access')
print('PASS: Monitor opens the shared PO form; draft/foreign-company records and Approver-only access remain denied.')
