"""Local Chromium fixture with actual shipped editors, mocked save/preview HTTP."""
from pathlib import Path
from html import escape
import json,re,os
from playwright.sync_api import sync_playwright
R=Path(os.environ.get('PBW_ADDON_PATH', Path(__file__).resolve().parents[2]))
OUT=Path(os.environ.get('PBW_QA_OUTPUT', Path.cwd()/'pbw_sales_browser_qa'));OUT.mkdir(parents=True,exist_ok=True)
boot={'default_taxes':[{'id':15,'label':'VAT 15%'}], 'order_id':501,'company_id':1,'version':'v1','editable':True,'currency':'SAR','untaxed':20,'tax':3,'total':23,'analytic_labels':{},'lines':[{'id':1,'product_id':2,'product':{'id':2,'label':'Product A'},'name':'Original quotation line','uom_id':1,'uom':{'id':1,'label':'Unit'},'quantity':2,'price_unit':10,'discount':0,'taxes_id':[15],'taxes':[{'id':15,'label':'VAT 15%'}],'analytic_distribution':{},'subtotal':20}]}
source='\n'.join(re.sub(r'^export ', '', re.sub(r'^import .*$', '', (R/'static/src/sales/js'/n).read_text(), flags=re.M),flags=re.M) for n in ('draft_navigation.js','line_grid.js','purchase_ui.js','analytic_editor.js','sales_lines.js'))
source=source[:source.rfind('function start()')]+'\nwindow.fixtureEditor=mountSalesLines(document.getElementById("pbw-sales-line-editor"));'
style='\n'.join((R/f).read_text() for f in ('static/src/sales/css/portal_sales.css','static/src/sales/css/purchase_controls.css','static/src/sales/css/sales_lines.css','static/src/sales/css/line_grid.css'))
results=[]
def check(name,value):
 results.append({'name':name,'passed':bool(value)})
 if not value:raise AssertionError(name)
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in (1440,390):
  page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:Arial;margin:14px}button{padding:8px}main{max-width:100%}.table-responsive{overflow:auto}</style></head><body><main class="pbw-sales-wrap"><h3>Sales confirmation fixture</h3><button data-sales-save="1">Save Draft</button><form id="confirm" method="post"><input name="csrf_token" type="hidden" value="fixture"><input name="action" type="hidden" value="confirm_direct"><button data-pbw-sales-confirm-direct="1">Confirm Sales Order</button></form><form id="pbw-sales-order-details"><label>Quotation date<input name="date_order" type="datetime-local" step="1" value="2026-11-07T12:00:00"></label><select name="project_id"><option value="11" selected>Existing construction project</option><option value="12">Another customer project</option></select><input name="validity_date" type="date" value="2026-12-01"></form><div id="pbw-sales-line-editor" data-csrf="fixture" data-boot="'''+escape(json.dumps(boot),quote=True)+'''"></div></main></body></html>''')
  page.add_style_tag(content=style)
  page.evaluate('''boot=>{window.fixtureCalls=[];window.fixtureSaved=boot;window.fetch=async(url,opts)=>{const payload=JSON.parse(opts.body.get('payload'));window.fixtureCalls.push({url,payload});let result;
   if(url.endsWith('/save')){result={...window.fixtureSaved,version:'v2',lines:payload.lines};window.fixtureSaved=result;}
   else if(url.endsWith('/preview'))result={untaxed:20,tax:3,total:23,line_amounts:payload.lines.map(()=>20)};
   else if(url.endsWith('/defaults'))result={...window.fixtureSaved.lines[0],quantity:payload.quantity};
   else if(url.endsWith('/lookup'))result={items:[],more:false};
   else throw Error(url);
   return new Response(JSON.stringify({ok:true,result}),{status:200,headers:{'Content-Type':'application/json'}});};}''',boot)
  page.add_script_tag(content=source)
  button=page.locator('[data-pbw-sales-confirm-direct]')
  check(f'{width}: saved own quotation can confirm',button.is_enabled())
  page.locator('input[name=date_order]').evaluate("el=>{el.value='2026-11-08T12:00';el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}")
  check(f'{width}: header edit disables confirm',button.is_disabled())
  page.locator('[data-sales-save]').click();page.wait_for_timeout(80)
  check(f'{width}: save restores confirm',button.is_enabled())
  page.locator('[data-sales-column="2"] input').fill('5')
  check(f'{width}: quantity edit disables confirm',button.is_disabled())
  prevented=page.evaluate('''()=>{const f=document.getElementById('confirm');const e=new Event('submit',{bubbles:true,cancelable:true});f.dispatchEvent(e);return e.defaultPrevented;}''')
  check(f'{width}: dirty form programmatic submit blocked',prevented)
  page.locator('[data-sales-save]').click();page.wait_for_timeout(100)
  check(f'{width}: saved quantity restores confirm',button.is_enabled())
  page.locator('select[name=project_id]').select_option('12')
  check(f'{width}: project change disables confirm',button.is_disabled())
  page.locator('[data-sales-save]').click();page.wait_for_timeout(100)
  check(f'{width}: mapped project sent in original header',page.evaluate("window.fixtureCalls.filter(c=>c.url.endsWith('/save')).at(-1).payload.header.project_id==='12'"))
  check(f'{width}: no JavaScript errors',not errors)
  page.screenshot(path=str(OUT/f'sales_confirm_{width}.png'),full_page=True)
  page.close()
 browser.close()
(OUT/'browser_results.json').write_text(json.dumps(results,indent=2))
print(f'{len(results)} actual-editor browser fixture checks passed (mocked HTTP, not live Odoo).')
