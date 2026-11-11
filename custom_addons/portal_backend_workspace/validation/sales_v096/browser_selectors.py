"""Local DOM fixtures from shipped QWeb, actual JS/CSS, mocked HTTP.
The small XML renderer below is NOT Odoo QWeb. No live Odoo claim is made.
"""
from pathlib import Path
from types import SimpleNamespace as NS
from html import escape
import copy,json,re,os
from lxml import etree as E
from playwright.sync_api import sync_playwright
R=Path(os.environ['PBW_ADDON_PATH']);B=Path(os.environ['PBW_SALES_BRIDGE_PATH'])
OUT=Path(os.environ.get('PBW_QA_OUTPUT','/mnt/data/pbw_sales_v096/qa/browser'));OUT.mkdir(parents=True,exist_ok=True)
templates={}
for n in E.parse(str(R/'views/sales/portal_sales_templates.xml')).getroot():
 if n.tag=='template':templates['portal_backend_workspace.'+n.get('id')]=copy.deepcopy(n)
for n in E.parse(str(B/'views/proposals.xml')).getroot():
 if n.get('inherit_id'):
  for x in n:
   for c in x:templates[n.get('inherit_id')].append(copy.deepcopy(c))

def val(expr,ctx):return eval(expr,{'__builtins__':{'str':str,'dict':dict,'len':len,'sum':sum,'list':list}},ctx)
def children(el,ctx):
 out=escape(el.text or '');branch=False
 for ch in el:
  if not isinstance(ch.tag,str):continue
  if 't-if' in ch.attrib:branch=bool(val(ch.get('t-if'),ctx));run=branch
  elif 't-elif' in ch.attrib:run=not branch and bool(val(ch.get('t-elif'),ctx));branch=branch or run
  elif 't-else' in ch.attrib:run=not branch;branch=True
  else:run=True;branch=False
  if run:out+=node(ch,ctx,conditional=False)
  out+=escape(ch.tail or '')
 return out

def node(el,ctx,conditional=True):
 if conditional and 't-if' in el.attrib and not val(el.get('t-if'),ctx):return ''
 if 't-foreach' in el.attrib:
  out='';items=list(val(el.get('t-foreach'),ctx));n=copy.deepcopy(el);del n.attrib['t-foreach'];name=n.attrib.pop('t-as')
  for i,x in enumerate(items):out+=node(n,{**ctx,name:x,name+'_index':i,name+'_last':i==len(items)-1},conditional=False)
  return out
 if 't-call' in el.attrib:
  target=el.get('t-call')
  return children(templates[target],ctx) if target in templates else children(el,ctx)
 if 't-set' in el.attrib:ctx[el.get('t-set')]=val(el.get('t-value'),ctx);return ''
 content=children(el,ctx)
 if 't-out' in el.attrib or 't-field' in el.attrib:
  value=val(el.get('t-out') or el.get('t-field'),ctx);content=escape('' if value is False or value is None else str(value))
 if el.tag in ('t','template'):return content
 attrs={k:v for k,v in el.attrib.items() if not k.startswith('t-')}
 for k,v in el.attrib.items():
  if k.startswith('t-att-'):
   v=val(v,ctx)
   if v is not None and v is not False:attrs[k[6:]]=str(v)
 attr=''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in attrs.items())
 if el.tag in ('input','br','img','meta','link'):return '<'+el.tag+attr+'>'
 return '<'+el.tag+attr+'>'+content+'</'+el.tag+'>'

class RS(list):
 def filtered(self,fn):return RS(x for x in self if fn(x))
 def sorted(self,key):return RS(sorted(self,key=key))
class Partner:
 def __init__(self,id,name,company=False):self.id=id;self.name=name;self.company_id=company;self.commercial_partner_id=self
class Empty:
 id=0;name='';
 def __bool__(self):return False
empty=Empty();c1=NS(id=1,name='Primary Company');c2=NS(id=2,name='Second Allowed Company')
p1=Partner(11,'Original checkbox customer',empty);p2=Partner(12,'Second-company customer',c2)
proj1=NS(id=21,name='Original customer project',partner_id=p1,company_id=empty)
proj2=NS(id=22,name='Second-company project',partner_id=p2,company_id=c2)
boot={'default_taxes':[{'id':15,'label':'VAT 15%'}],'order_id':0,'company_id':1,'version':'','editable':True,'currency':'SAR','untaxed':0,'tax':0,'total':0,'analytic_labels':{},'lines':[]}
class User:
 def has_group(self,g):return True
request=NS(env=NS(user=User(),company=c1),httprequest=NS(path='/my/workspace/sales/new'),csrf_token=lambda:'fixture',params={})
common={'request':request,'error':False,'date_order_local':'2026-11-08T12:30:00','line_boot_json':json.dumps(boot),'partners':[p1,p2],'projects':[proj1,proj2],'quotation_company':c1,'customer_source_labels':['Workspace Customer / Client','Customer / Client (original Sales)']}
css='\n'.join((R/f).read_text() for f in ('static/src/sales/css/portal_sales.css','static/src/sales/css/purchase_controls.css','static/src/sales/css/sales_lines.css','static/src/sales/css/line_grid.css'))
basecss='''*{box-sizing:border-box}body{margin:0;background:#f0f2f6;color:#172c3b;font:15px Arial}main{padding:20px;min-width:0;max-width:100%}.container{width:100%;max-width:100%}.row{display:flex;flex-wrap:wrap;margin:0 -8px}.row>*{padding:8px;width:100%;min-width:0}.col-12{width:100%}.form-control,.form-select{width:100%;padding:9px;border:1px solid #d9dee4;border-radius:6px;background:white;color:inherit;font:inherit}.btn{border:1px solid #d9dee4;border-radius:6px;padding:9px 14px;cursor:pointer;background:white;color:inherit;font:inherit}.btn-primary{background:#00878c;color:white}.text-muted{color:#71808a}.small,small{font-size:12px}.table{width:100%;border-collapse:collapse}.table td,.table th{padding:8px}.table-responsive{max-width:100%;overflow:auto}.d-flex{display:flex;flex-wrap:wrap}.gap-2{gap:8px}.gap-3{gap:12px}.my-3,.mb-3,.mb-4{margin-bottom:16px}label{display:block;margin-bottom:5px}h3{font-size:26px}h5{font-size:19px}.alert{padding:12px;background:#fff5d9}.mt-2,.mt-3{margin-top:12px}@media(min-width:768px){.col-md-6{width:50%}.col-md-8{width:66.67%}.col-md-4{width:33.33%}.col-md-5{width:41.67%}.col-md-3{width:25%}.col-md-2{width:16.67%}}'''
js=(R/'static/src/sales/js/portal_sales.js').read_text()
editor='\n'.join(re.sub(r'^export ','',re.sub(r'^import .*$', '',(R/'static/src/sales/js'/n).read_text(),flags=re.M),flags=re.M) for n in ('draft_navigation.js','line_grid.js','purchase_ui.js','analytic_editor.js','sales_lines.js'))
editor=editor[:editor.rfind('function start()')]+'\nwindow.fixtureEditor=mountSalesLines(document.getElementById("pbw-sales-line-editor"));'
results=[]
def check(name,result):
 results.append({'name':name,'passed':bool(result)})
 if not result:raise AssertionError(name)
def render(template,ctx):
 return '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+basecss+css+'</style></head><body><main>'+children(templates[template],ctx)+'</main></body></html>'

with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in (1440,390):
  page=browser.new_page(viewport={'width':width,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  context={**common,'document_types':[('standard','Standard Quotation'),('technical','Technical & Financial Proposal')]}
  page.set_content(render('portal_backend_workspace.sales__sales_new',context))
  page.evaluate('''()=>{window.calls=[];window.fetch=async(url,opts)=>{const p=JSON.parse(opts.body.get('payload'));calls.push({url,p});let result={};
   if(url.endsWith('search-more'))return new Response(JSON.stringify({items:[{id:12,name:'Second-company customer',customer_id:12,company_id:2,company_name:'Second Allowed Company'}],more:false}),{headers:{'Content-Type':'application/json'}});
   if(url.endsWith('/preview')){const second=p.header.partner_id==='12';result={untaxed:0,tax:0,total:0,line_amounts:[],company_id:second?2:1,company_name:second?'Second Allowed Company':'Primary Company',currency:second?'EUR':'SAR',default_taxes:[]};}
   if(url.endsWith('/create'))result={order_id:0,company_id:2,version:'saved',editable:true,lines:[],analytic_labels:{},currency:'EUR',untaxed:0,tax:0,total:0,default_taxes:[]};
   return new Response(JSON.stringify({ok:true,result}),{headers:{'Content-Type':'application/json'}});};}''')
  page.add_script_tag(content=js);page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))");page.add_script_tag(content=editor)
  check(f'{width} customer options have actual choices',page.locator('select[name=partner_id] option').count()==3)
  check(f'{width} document types include technical',page.locator('select[name=kind] option[value=technical]').count()==1)
  page.locator('select[name=partner_id]').select_option('12');page.wait_for_timeout(400)
  check(f'{width} quotation company follows customer',page.locator('[data-sales-company-name]').inner_text()=='Second Allowed Company')
  check(f'{width} wrong-customer project disabled',page.locator('select[name=project_id] option[value="21"]').is_disabled())
  check(f'{width} correct company project selectable',not page.locator('select[name=project_id] option[value="22"]').is_disabled())
  page.locator('select[name=project_id]').select_option('22');page.locator('select[name=kind]').select_option('technical')
  page.locator('[data-sales-save]').click();page.wait_for_timeout(150)
  payload=page.evaluate("calls.filter(c=>c.url.endsWith('/create')).at(-1).p.header")
  check(f'{width} technical document type reaches save',payload['kind']=='technical')
  check(f'{width} chosen customer and project reach save',payload['partner_id']=='12' and payload['project_id']=='22')
  page.locator('select[name=partner_id] + button').click();page.wait_for_timeout(80)
  check(f'{width} search more uses live lookup',page.locator('dialog').inner_text().find('Second-company customer')!=-1)
  page.locator('dialog').get_by_role('button',name='Second-company customer',exact=True).click()
  check(f'{width} search result retains company metadata',page.locator('select[name=partner_id] option:checked').get_attribute('data-company-id')=='2')
  check(f'{width} no JS errors',not errors)
  page.screenshot(path=str(OUT/f'new_sales_{width}.png'),full_page=True)
  # Base without the optional engine must retain standard, without broken fields.
  page.set_content(render('portal_backend_workspace.sales__sales_new',{**common,'partners':[],'document_types':[('standard','Standard Quotation')],'customer_source_labels':['Workspace Customer / Client']}))
  check(f'{width} standalone only exposes working standard type',page.locator('select[name=kind] option').count()==1)
  check(f'{width} empty-customer reason is displayed',page.locator('.pbw-sales-empty-customers').is_visible())
  page.close()
 # Original proposal controls: actual migrated markup with fake records.
 for width in (1440,390):
  page=browser.new_page(viewport={'width':width,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  section=NS(id=1,sequence=10,name='Executive Summary',section_type='executive',content='<p>Existing proposal text</p>',include_in_report=True,page_break_before=False,_fields={'section_type':NS(selection=[('executive','Executive Summary'),('custom','Custom Section')])})
  order=NS(order_line=RS([NS(display_type=False)]),id=501,name='Q00501',partner_id=p1,pbw_portal_creator_id=NS(name='Preparer'),pbw_portal_review_state='draft',pbw_order_review_state='none',pbw_portal_review_note='',user_id=NS(name='Preparer'),validity_date='2026-12-01',date_order='2026-11-08',state='draft',_fields={'state':NS(selection=[('draft','Quotation')])},
   absar_proposal_type='technical',absar_proposal_title='TECHNICAL & FINANCIAL PROPOSAL',absar_proposal_template_id=NS(name='Original template'),absar_proposal_section_ids=RS([section]),absar_proposal_payment_ids=RS([NS(id=1,name='Advance',percentage=100,due_condition='On order')]),_pbw_sales_document_type=lambda:'technical',_pbw_sales_document_label=lambda:'Technical & Financial Proposal',_pbw_sales_project=lambda:proj1,env={'absar.proposal.section':NS(_fields=section._fields)})
  req=copy.copy(request);req.httprequest=NS(path='/my/workspace/sales/501')
  ctx={**common,'request':req,'order':order,'projects':[proj1],'templates':[NS(id=10,name='Original template')],'can_edit':True,'can_print':True,'can_confirm':False,'can_confirm_direct':True,'can_approve':False,'can_approve_order':False,'can_submit':False,'can_request_order':False,'can_return':False,'line_boot_json':json.dumps({**boot,'order_id':501,'version':'v1'})}
  page.set_content(render('portal_backend_workspace.sales__sales_detail',ctx));page.add_script_tag(content=js);page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))");page.add_script_tag(content=editor)
  check(f'{width} saved proposal label not standard',page.locator('body').inner_text().count('Technical & Financial Proposal')>=1)
  check(f'{width} original template control present',page.locator('select[name=template_id]').count()==1)
  check(f'{width} proposal title editable',page.locator('input[name=title]').is_visible())
  page.locator('details.pbw-sales-section > summary').click()
  check(f'{width} section rich text control expands',page.locator('.pbw-sales-editor-body').is_visible())
  page.locator('.pbw-sales-editor-body').fill('Updated technical section')
  check(f'{width} content syncs to posted field',page.locator('textarea[name=content]').first.input_value()=='Updated technical section')
  check(f'{width} milestones retain controls',page.locator('input[name=percentage]').is_visible())
  check(f'{width} section writes route to PBW not EPS',page.locator('form[action$="/section/1/save"]').get_attribute('action')=='/my/workspace/sales/501/section/1/save')
  check(f'{width} no detail JS errors',not errors)
  page.screenshot(path=str(OUT/f'technical_detail_{width}.png'),full_page=True);page.close()
 browser.close()
(OUT/'results.json').write_text(json.dumps(results,indent=2));print(f'{len(results)} local DOM assertions passed. Mocked data and HTTP, not live Odoo.')
