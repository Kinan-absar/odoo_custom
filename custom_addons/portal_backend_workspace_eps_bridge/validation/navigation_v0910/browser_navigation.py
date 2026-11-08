"""Local QWeb-derived rendering and real shipped CSS/JS, not an Odoo server.
The fixture renderer only implements directives used by the tested shell/home.
"""
import ast
import copy
from html import escape
import json
import re
from pathlib import Path
from types import SimpleNamespace as NS
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
from lxml import etree as E
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'portal_backend_workspace'
BRIDGE=ROOT/'portal_backend_workspace_eps_bridge'
OUT=ROOT/'qa'
DOC=E.parse(str(BASE/'views/workspace_layout.xml'))
TEMPLATES={'portal_backend_workspace.'+n.get('id'):n for n in DOC.xpath('//template')}
N=E.parse(str(BASE/'views/notification_assets.xml'))
TEMPLATES.update({'portal_backend_workspace.'+n.get('id'):n for n in N.xpath('//template')})
EPS=E.parse(str(ROOT/'reference/employee_portal_layout.xml'))
EPS_LAYOUT=EPS.xpath('//template[@id="employee_portal_layout"]')[0]
EPS_CSS='\n'.join(''.join(n.itertext()) for n in EPS_LAYOUT.xpath('.//style'))
EPS_SIDEBAR=copy.deepcopy(EPS_LAYOUT.xpath('.//aside[@id="ep-shared-sidebar"]')[0])
# Apply the shipped bridge inheritance to the actual original EPS sidebar.
NAV=E.parse(str(BRIDGE/'views/navigation.xml'))
for xp in NAV.xpath('//xpath'):
 if "ep-desktop-sidebar-nav" in xp.get('expr'):
  target=EPS_SIDEBAR.xpath('.//nav[@id="ep-desktop-sidebar-nav"]')[0]
  for child in xp: target.addprevious(copy.deepcopy(child))
# Inline navigation scripts already present in EPS aren't part of this UI patch.
for script in EPS_SIDEBAR.xpath('.//script'): script.getparent().remove(script)

# Bind the shipped permission/navigation methods to a controlled fixture user.
source=ast.parse((BASE/'models/workspace.py').read_text())
cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='WorkspaceUser')
methods=ast.ClassDef(name='Permissions',bases=[],keywords=[],body=copy.deepcopy(cls.body),decorator_list=[])
scope={'_':lambda s:s}
for n in source.body:
 if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('PREFIX','AREAS') for t in n.targets):
  exec(compile(ast.Module(body=[n],type_ignores=[]),'<actual constants>','exec'),scope)
exec(compile(ast.fix_missing_locations(ast.Module(body=[methods],type_ignores=[])),'<actual navigation methods>','exec'),scope)
class User(scope['Permissions']):
 def __init__(self, mode='integrated'):
  self.active=True;self.share=True;self.name='Test User';self.company_id=NS(id=1,name='Demo Company');self.employee_id=NS(id=1,job_title='Employee')
  self.partner_id=NS(avatar_128='');self.mode=mode
  self.groups={scope['PREFIX']+'group_workspace_access'}
  if mode!='eps_only':
   self.groups.update(scope['PREFIX']+g for g in (
     'sales__group_portal_sales_creator','sales__group_portal_sales_user',
     'purchase__group_portal_purchase_preparer','accounting__group_accountant',
     'accounting__group_customer_invoicing','hr__group_employee_admin'))
  else:self.groups.clear()
  if mode=='limited':self.groups={scope['PREFIX']+'group_workspace_access',scope['PREFIX']+'sales__group_portal_sales_creator'}
 def ensure_one(self):pass
 def _is_public(self):return False
 def has_group(self,g):return g in self.groups
 def sudo(self):return self
 def with_company(self,c):return self
 def _pbw_extra_navigation(self):return [{'name':'Employee Portal','url':'/my/employee'}] if self.mode in ('integrated','limited') else []

DATA={'items':[{'key':'pbw:1','id':1,'source':'workspace','category':'sales','title':'Quotation S00513 review update','body':'Approved.','count':1,'url':'/my/workspace/notifications/1/open','date':'2026-11-08 13:00:00'}], 'unread_count':1,'workspace_unread_count':1,'workspace_watermark':1,'history_url':'/my/workspace/notifications','workspace_summary':{}}
class Env:
 def __init__(self,u):self.user=u;self.company=u.company_id
 def __getitem__(self,k):return NS(_get_bell_data=lambda u:copy.deepcopy(DATA))
VOID={'link','meta','img','input','br','hr','source','wbr','area','embed','param','col','base'}
def ev(expr,ctx):
 if expr=='0':return ctx.get('0','')
 return eval(expr,{},ctx)
def children(n,ctx):
 return escape(n.text or '')+''.join(render(c,ctx)+escape(c.tail or '') for c in n)
def render(n,ctx,looped=False):
 if not isinstance(n.tag,str):return ''
 if 't-foreach' in n.attrib and not looped:
  result=[];items=ev(n.get('t-foreach'),ctx)
  for i,item in enumerate(items):
   local=ctx.copy();local.update({n.get('t-as'):item,n.get('t-as')+'_index':i})
   result.append(render(n,local,True))
  return ''.join(result)
 if 't-if' in n.attrib and not ev(n.get('t-if'),ctx):return ''
 if 't-set' in n.attrib:
  ctx[n.get('t-set')]=ev(n.get('t-value'),ctx) if 't-value' in n.attrib else children(n,ctx)
  return ''
 if 't-call-assets' in n.attrib:return ''
 if 't-call' in n.attrib:
  local=ctx.copy();body=children(n,local);local['0']=body
  key=n.get('t-call')
  return body if key=='web.layout' else render(TEMPLATES[key],local)
 if 't-out' in n.attrib:
  content=str(ev(n.get('t-out'),ctx)) if n.get('t-out')=='0' else escape(str(ev(n.get('t-out'),ctx)))
 else:content=children(n,ctx)
 if n.tag in ('t','template'):return content
 attrs=[]
 for k,v in n.attrib.items():
  if k.startswith('t-att-'):
   value=ev(v,ctx)
   if value is None or value is False:continue
   attrs.append((k[6:],str(value)))
  elif not k.startswith('t-') and k not in ('inherit_id',):attrs.append((k,v))
 start='<'+n.tag+''.join(' %s="%s"'%(k,escape(v,quote=True)) for k,v in attrs)+'>'
 return start if n.tag in VOID else start+content+'</'+n.tag+'>'

STUB='data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="40" height="40"%3E%3C/svg%3E'
SCAFFOLD='''body{margin:0}a{text-decoration:none}button{font:inherit}.container{width:100%;margin-right:auto;margin-left:auto;padding-right:12px;padding-left:12px}.d-block{display:block}.ms-auto{margin-left:auto}.text-muted{color:#637280}.mb-4{margin-bottom:24px}.py-3{padding-top:16px;padding-bottom:16px}.btn{display:inline-block}h1,h2,h3,p{margin-top:0}h1{margin-bottom:8px}p{margin-bottom:16px}button{cursor:pointer}.fa{display:inline-block;width:1em;height:1em;font-style:normal}.fa:before{content:"\\25A1"}'''
# Square icons above only stand in for Odoo's bundled Font Awesome in the fixture;
# production markup and the application stylesheet/geometry are unchanged.
DENSITY='@media screen and (min-width:769px){html{zoom:.8}}'
def page_html(mode,shell='workspace',accounting=False):
 u=User(mode);ctx={'request':NS(env=Env(u),csrf_token=lambda:'fixture-csrf'),'image_data_uri':lambda _:STUB,'workspace_areas':u._pbw_workspace_areas(),'workspace_attention':[], 'pbw_bell_data':copy.deepcopy(DATA),'ep_notif_summary':{},'can_er_approval_nav':False,'can_mr_approval_nav':False}
 assets=''.join('<link rel="stylesheet" href="/portal_backend_workspace/'+p+'">' for p in ('static/src/accounting/accounting.css',))
 if shell=='workspace':
  content=render(TEMPLATES['portal_backend_workspace.workspace_home'],ctx)
  if accounting:
   from lxml import html
   h=html.fromstring(content)
   cards=h.xpath('//*[contains(@class,"pbw-workspace-home-cards")]')[0]
   cards.set('class','pbw-accounting-cards')
   content=E.tostring(h,method='html',encoding='unicode')
 else:
  assets+='<link rel="stylesheet" href="/fixture/eps.css"><link rel="stylesheet" href="/portal_backend_workspace/static/src/core/workspace_navigation.css">'
  content='<button type="button" class="ep-mobile-menu-backdrop mobile-only" data-ep-menu-close="1" hidden></button>'+render(EPS_SIDEBAR,ctx)
  bell=render(TEMPLATES['portal_backend_workspace.notification_bell'],ctx)
  content+='<div class="ep-desktop-top-actions">'+bell+'</div><div class="ep-mobile-topbar mobile-only"><button type="button" class="ep-mobile-menu-toggle" aria-label="Open navigation" aria-controls="ep-shared-sidebar" aria-expanded="false">Menu</button>'+bell+'</div><main class="ep-portal-main"><div id="wrap" class="container"><h1>Employee Portal</h1><p>Local UI test fixture</p></div></main>'
  content+=render(TEMPLATES['portal_backend_workspace.notification_assets'],ctx)+'<script src="/fixture/eps-menu.js"></script>'
 return '<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>'+SCAFFOLD+DENSITY+'</style>'+assets+'</head><body>'+content+'</body></html>'

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  p=urlparse(self.path);q=parse_qs(p.query)
  if p.path in ('/my/workspace','/my/employee','/fixture/accounting'):
   body=page_html(q.get('mode',['integrated'])[0], 'eps' if p.path=='/my/employee' else 'workspace',p.path=='/fixture/accounting').encode();ct='text/html'
  elif p.path=='/my/workspace/notifications/bell':body=json.dumps(DATA).encode();ct='application/json'
  elif p.path=='/fixture/eps.css':body=EPS_CSS.encode();ct='text/css'
  elif p.path=='/fixture/eps-menu.js':body=(ROOT/'reference/portal_mobile_menu.js').read_bytes();ct='text/javascript'
  elif p.path.startswith('/portal_backend_workspace/static/'):
   f=BASE/p.path.split('/portal_backend_workspace/',1)[1]
   body=f.read_bytes();ct='text/css' if f.suffix=='.css' else 'text/javascript'
  elif p.path.startswith('/web/image/'):
   body=b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" rx="10" fill="#087f83"/><text x="20" y="28" font-family="sans-serif" font-size="24" text-anchor="middle" fill="white">W</text></svg>';ct='image/svg+xml'
  else:body=b'<html><body>Local test destination</body></html>';ct='text/html'
  self.send_response(200);self.send_header('Content-Type',ct);self.end_headers();self.wfile.write(body)

RESULTS=[]
def check(name,value,detail=None):
 RESULTS.append({'name':name,'passed':bool(value),'detail':detail})
 if not value:raise AssertionError(name+': '+str(detail))
def mount(page, mode='integrated', shell='workspace', accounting=False):
    raw=page_html(mode,shell,accounting)
    styles=[]
    for href in re.findall(r'<link[^>]*href="([^"]+)"[^>]*>',raw):
        path=href.split('?')[0]
        if path.startswith('/portal_backend_workspace/'):
            styles.append((BASE/path.split('/portal_backend_workspace/',1)[1]).read_text())
        elif path=='/fixture/eps.css':styles.append(EPS_CSS)
    raw=re.sub(r'<link[^>]*>|<script\b[^>]*>.*?</script>', '', raw, flags=re.S)
    raw=re.sub(r'(<img[^>]*src=")[^"]*(")', lambda m:m[1]+STUB+m[2],raw)
    page.set_content(raw)
    for css in styles:page.add_style_tag(content=css)
    page.evaluate("""data => {
        window.__clickedHref = null;
        document.addEventListener('click', e => {
            const a=e.target.closest('a[href]');
            if(a){e.preventDefault();window.__clickedHref=a.getAttribute('href');}
        });
        window.fetch=async () => new Response(JSON.stringify(data), {status:200,headers:{'Content-Type':'application/json'}});
    }""",DATA)
    # about:blank has an opaque origin; this fixture-only adapter gives the
    # unchanged relative-link validator a same-origin reference.
    bell=(BASE/'static/src/core/notification_bell.js').read_text().replace('location.origin', "'https://pbw-fixture.invalid'")
    page.add_script_tag(content=bell)
    if shell=='workspace':
        page.add_script_tag(content=(BASE/'static/src/core/portal_mobile_menu.js').read_text())
        page.add_script_tag(content=(BASE/'static/src/core/workspace_shell.js').read_text().replace('location.origin', "'https://pbw-fixture.invalid'"))
    else:page.add_script_tag(content=(ROOT/'reference/portal_mobile_menu.js').read_text())
    page.wait_for_timeout(60)

try:
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for mode in ('standalone','integrated','limited'):
   for width in (1440,1024,768,390,320):
    ctx=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce')
    page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('https://**/*',lambda r:r.abort())
    mount(page,mode)
    cards=page.locator('.pbw-workspace-home-cards > a')
    check(f'{mode}/{width}: cards match role',cards.count()==(1 if mode=='limited' else 4))
    check(f'{mode}/{width}: no menu history',page.locator('#pbwep-desktop-sidebar-nav a[href="/my/workspace/notifications"]').count()==0)
    check(f'{mode}/{width}: no portal link mixed in menu',page.locator('#pbwep-desktop-sidebar-nav a[href="/my/employee"]').count()==0)
    check(f'{mode}/{width}: correct switch presence',page.locator('.pbw-portal-switch-link').count()==(0 if mode=='standalone' else 1))
    check(f'{mode}/{width}: no nested card links',page.locator('.pbw-workspace-home-cards > a a').count()==0)
    dims=page.evaluate('''() => ({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,columns:getComputedStyle(document.querySelector('.pbw-workspace-home-cards')).gridTemplateColumns.split(' ').length})''')
    check(f'{mode}/{width}: no horizontal page overflow',dims['scroll']<=dims['client']+1,dims)
    check(f'{mode}/{width}: responsive grid',dims['columns']==(4 if width>1100 else 2 if width>480 else 1),dims)
    check(f'{mode}/{width}: one visible bell',page.locator('.pbw-notification-trigger:visible').count()==1)
    page.locator('.pbw-notification-trigger:visible').click()
    check(f'{mode}/{width}: bell has history',page.locator('[data-pbw-history]:visible').get_attribute('href')=='/my/workspace/notifications')
    page.keyboard.press('Escape')
    if mode=='integrated' and width in (1440,390):page.screenshot(path=str(OUT/f'workspace_{width}.png'),full_page=True)
    if width<=768:
     page.locator('.pbwep-mobile-menu-toggle:visible').click()
     check(f'{mode}/{width}: drawer open',page.locator('#pbwep-shared-sidebar').is_visible())
     if mode!='standalone':
      sw=page.locator('.pbw-portal-switch-link');check(f'{mode}/{width}: switch in drawer',sw.is_visible())
      box=sw.bounding_box();check(f'{mode}/{width}: mobile target size',box['height']>=44,box)
      if width==390 and mode=='integrated':page.screenshot(path=str(OUT/'workspace_drawer_390.png'))
      sw.focus();check(f'{mode}/{width}: keyboard focus',sw.evaluate('(e)=>e===document.activeElement'))
     page.keyboard.press('Escape')
     check(f'{mode}/{width}: escape closes drawer',not page.locator('#pbwep-shared-sidebar').is_visible())
    elif mode!='standalone':
     box=page.locator('.pbw-portal-switch-link').bounding_box()
     navbox=page.locator('#pbwep-desktop-sidebar-nav').bounding_box()
     check(f'{mode}/{width}: switch above menu',box['y']+box['height']<=navbox['y'])
    check(f'{mode}/{width}: no script errors',not errors,errors)
    ctx.close()
  for mode in ('integrated','eps_only'):
   for width in (1440,390):
    ctx=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce');page=ctx.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    mount(page,mode,'eps')
    check(f'EPS/{mode}/{width}: switch permission gate',page.locator('.pbw-portal-switch-link').count()==(1 if mode=='integrated' else 0))
    check(f'EPS/{mode}/{width}: no workspace section in menu',page.locator('#pbw-eps-business-workspaces').count()==0)
    check(f'EPS/{mode}/{width}: no workspace links in menu',page.locator('#ep-desktop-sidebar-nav a[href^="/my/workspace"]').count()==0)
    if width==390:page.locator('.ep-mobile-menu-toggle:visible').click()
    if mode=='integrated':
     sw=page.locator('.pbw-portal-switch-link');check(f'EPS/{mode}/{width}: switch visible',sw.is_visible())
     check(f'EPS/{mode}/{width}: switch destination',sw.get_attribute('href')=='/my/workspace')
     page.screenshot(path=str(OUT/f'employee_{width}.png'),full_page=width>390)
     sw.click()
     check(f'EPS/{mode}/{width}: switch activates workspace link',page.evaluate('window.__clickedHref')=='/my/workspace')
     page=ctx.new_page();mount(page,mode)
     if width==390:page.locator('.pbwep-mobile-menu-toggle:visible').click()
     page.locator('.pbw-portal-switch-link').click()
     check(f'EPS/{mode}/{width}: switch activates employee link',page.evaluate('window.__clickedHref')=='/my/employee')
    check(f'EPS/{mode}/{width}: no script errors',not errors,errors)
    ctx.close()
  # Exact computed styles match the existing Accounting component at the same width.
  for width in (1440,390):
   ctx=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce');page=ctx.new_page()
   page.route('https://**/*',lambda r:r.abort());mount(page)
   props=['height','borderRadius','backgroundImage','paddingTop','fontFamily','boxShadow','gap']
   js='(props)=>Object.fromEntries(props.map(k=>[k,getComputedStyle(document.querySelector(".pbw-accounting-cards > a"))[k]]))'
   home=page.evaluate(js,props);page=ctx.new_page();mount(page,accounting=True);accounting=page.evaluate(js,props)
   check(f'{width}: exact Accounting tile styles',home==accounting,{'home':home,'accounting':accounting})
   ctx.close()
  browser.close()
finally:
 (OUT/'browser_results.json').write_text(json.dumps(RESULTS,indent=2))
 print(sum(r['passed'] for r in RESULTS),'of',len(RESULTS),'browser assertions passed')
