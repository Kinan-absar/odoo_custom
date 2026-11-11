"""Actual shipped frontend scripts and QWeb-derived fixtures with mocked HTTP.
Limited renderer, not Odoo QWeb or a live Odoo server.
"""
from pathlib import Path
from types import SimpleNamespace as NS
from html import escape
import copy,json,re,os
from lxml import etree as E
from playwright.sync_api import sync_playwright
R=Path(os.environ['PBW_ADDON_PATH']);B=Path(os.environ['PBW_SALES_BRIDGE_PATH'])
OUT=Path(__file__).parent/'browser';OUT.mkdir(exist_ok=True)
templates={}
for n in E.parse(str(R/'views/sales/portal_sales_templates.xml')).getroot():
 if n.tag=='template':templates['portal_backend_workspace.'+n.get('id')]=copy.deepcopy(n)
for n in E.parse(str(B/'views/proposals.xml')).getroot():
 if not n.get('inherit_id'):continue
 target=templates[n.get('inherit_id')]
 for x in n:
  for match in list(target.xpath(x.get('expr'))):
   if x.get('position')=='inside':
    for child in x:match.append(copy.deepcopy(child))
   elif x.get('position')=='after':
    at=match
    for child in x:
     child=copy.deepcopy(child);at.addnext(child);at=child
   else:raise AssertionError('unsupported position')

def val(expr,ctx):return eval(expr,{'__builtins__':{'str':str,'dict':dict,'len':len,'sum':sum,'list':list}},ctx)
def children(el,ctx):
 out=escape(el.text or '');branch=False
 for ch in el:
  if not isinstance(ch.tag,str):continue
  if 't-foreach' in ch.attrib:run=True;branch=False
  elif 't-if' in ch.attrib:branch=bool(val(ch.get('t-if'),ctx));run=branch
  elif 't-elif' in ch.attrib:run=not branch and bool(val(ch.get('t-elif'),ctx));branch=branch or run
  elif 't-else' in ch.attrib:run=not branch;branch=True
  else:run=True;branch=False
  if run:out+=node(ch,ctx,conditional='t-foreach' in ch.attrib)
  out+=escape(ch.tail or '')
 return out

def node(el,ctx,conditional=True):
 if 't-foreach' in el.attrib:
  out='';items=list(val(el.get('t-foreach'),ctx));n=copy.deepcopy(el);del n.attrib['t-foreach'];name=n.attrib.pop('t-as')
  for i,x in enumerate(items):out+=node(n,{**ctx,name:x,name+'_index':i,name+'_last':i==len(items)-1})
  return out
 if conditional and 't-if' in el.attrib and not val(el.get('t-if'),ctx):return ''
 if 't-call' in el.attrib:
  target=el.get('t-call');return children(templates[target],ctx) if target in templates else children(el,ctx)
 if 't-set' in el.attrib:ctx[el.get('t-set')]=val(el.get('t-value'),ctx);return ''
 content=children(el,ctx)
 if 't-out' in el.attrib or 't-field' in el.attrib:
  expr=el.get('t-out') or el.get('t-field');value=val(expr,ctx);content='' if value is False or value is None else str(value)
  if el.get('t-field')!='s.content':content=escape(content)
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
 def sorted(self,key):return RS(sorted(self,key=key if callable(key) else lambda x:getattr(x,key)))
 def mapped(self,name):return [getattr(x,name) for x in self]
class Record(NS):
 def __getitem__(self,key):return getattr(self,key)
class Partner:
 def __init__(self,id,name,company):self.id=id;self.name=name;self.company_id=company;self.commercial_partner_id=self
class Empty:
 id=0;name=''
 def __bool__(self):return False
empty=Empty();c1=NS(id=1,name='Primary Company');c2=NS(id=2,name='Second Company')
p1=Partner(11,'Original Customer / Client enabled',empty);p2=Partner(12,'Second Company Customer',c2)
boot={'default_taxes':[{'id':15,'label':'VAT 15%'}],'order_id':0,'company_id':1,'version':'','editable':True,'currency':'SAR','untaxed':0,'tax':0,'total':0,'analytic_labels':{},'lines':[]}
request=NS(env=NS(user=NS(has_group=lambda g:True),company=c1),httprequest=NS(path='/my/workspace/sales/new'),csrf_token=lambda:'fixture',params={})
proposalboot={'types':[['executive','Executive Summary'],['confirmation','Confirmation'],['custom','Custom Section']], 'defaults':{k:{'section_type':k,'name':n,'content':'<p>Native confirmation</p>' if k=='confirmation' else '', 'include_in_report':True,'page_break_before':False} for k,n in [('executive','Executive Summary'),('confirmation','Confirmation'),('custom','Custom Section')]}}
headerfields={key:'absar_proposal_'+key for key in ['title','reference','signatory','signatory_title','customer_signatory','customer_signatory_title']}
common={'request':request,'error':False,'date_order_local':'2026-11-08T12:30:00','line_boot_json':json.dumps(boot),'partners':[p1,p2],'projects':[], 'templates':[NS(id=10,name='Original technical template',company_id=c1),NS(id=11,name='Other company template',company_id=c2)], 'quotation_company':c1,'customer_source_labels':['Customer / Client'],'proposal_supported':True,'proposal_header_fields':headerfields,'proposal_draft_boot':json.dumps(proposalboot),'document_types':[('standard','Standard Quotation'),('technical','Technical & Financial Proposal')]}
# Use the previous documented fixture's bootstrap subset; original shipped styles
# are layered on top. This is deliberately not claimed as a full website render.
old=(R/'validation/sales_v096/browser_selectors.py').read_text()
basecss=old.split("basecss='''",1)[1].split("'''",1)[0]
css='\n'.join((R/f).read_text() for f in ['static/src/sales/css/portal_sales.css','static/src/sales/css/purchase_controls.css','static/src/sales/css/sales_lines.css','static/src/sales/css/line_grid.css'])+'\n'+(B/'static/src/proposal_draft.css').read_text()
js=(R/'static/src/sales/js/portal_sales.js').read_text()
editor='\n'.join(re.sub(r'^export ','',re.sub(r'^import .*$', '',(R/'static/src/sales/js'/name).read_text(),flags=re.M),flags=re.M) for name in ['draft_navigation.js','line_grid.js','purchase_ui.js','analytic_editor.js','sales_lines.js'])
editor=editor[:editor.rfind('function start()')]+'\nwindow.fixtureEditor=mountSalesLines(document.getElementById("pbw-sales-line-editor"));'
draft=re.sub(r'^export ','',(B/'static/src/proposal_draft.js').read_text(),flags=re.M)
draft=draft[:draft.rfind('function start()')]+'\nwindow.fixtureProposal=mountProposalDraft(document.getElementById("pbw-proposal-draft-editor"));'
results=[]
def check(name,passed):
 results.append({'name':name,'passed':bool(passed)})
 if not passed:raise AssertionError(name)
def render(which,ctx):
 return '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+basecss+css+'</style></head><body><main>'+children(templates[which],ctx)+'</main></body></html>'
fetch='''()=>{window.calls=[];window.fetch=async(url,opts)=>{const data=Object.fromEntries(opts.body.entries());const p=data.payload?JSON.parse(data.payload):data;calls.push({url,p});
 if(url.endsWith('proposal-template-preview'))return new Response(JSON.stringify({title:'Loaded Technical Proposal',template_id:10,company_id:1,sections:[{section_type:'executive',name:'Executive Summary',content:'<p>Original scope</p>',include_in_report:true,page_break_before:false},{section_type:'confirmation',name:'Confirmation',content:'<p>Confirm the order</p>',include_in_report:true,page_break_before:true}],payments:[{name:'Advance',percentage:75,due_condition:'On order'},{name:'Handover',percentage:25,due_condition:'At handover'}]}),{headers:{'Content-Type':'application/json'}});
 let result={};if(url.endsWith('/preview'))result={untaxed:1000,tax:150,total:1150,line_amounts:[],company_id:1,company_name:'Primary Company',currency:'SAR',default_taxes:[]};
 if(url.endsWith('/create'))result={order_id:0,company_id:1,editable:true,version:'v1',lines:[],analytic_labels:{},currency:'SAR',untaxed:1000,tax:150,total:1150,default_taxes:[]};
 return new Response(JSON.stringify({ok:true,result}),{headers:{'Content-Type':'application/json'}});};}'''
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 for width in [1440,390]:
  page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.set_content(render('portal_backend_workspace.sales__sales_new',common));page.evaluate(fetch)
  page.add_script_tag(content=js);page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))");page.add_script_tag(content=editor);page.add_script_tag(content=draft)
  check(f'{width} standard has no technical panels',not page.locator('#pbw-proposal-draft-editor').is_visible())
  page.locator('select[name=partner_id]').select_option('11');page.locator('select[name=kind]').select_option('technical')
  check(f'{width} sections appear before save',page.locator('#pbw-proposal-draft-editor').is_visible())
  check(f'{width} header title and reference available',page.locator('[name=title]').is_visible() and page.locator('[name=reference]').is_visible())
  check(f'{width} no quotation created by choosing type',page.evaluate("calls.filter(c=>c.url.endsWith('/create')).length")==0)
  check(f'{width} foreign template disabled',page.locator('select[name=template_id] option[value="11"]').is_disabled())
  page.locator('select[name=template_id]').select_option('10');page.locator('[data-pbw-proposal-load]').click();page.wait_for_timeout(350)
  check(f'{width} native template title loaded',page.locator('[name=title]').input_value()=='Loaded Technical Proposal')
  check(f'{width} native template sections loaded',page.locator('#pbw-proposal-draft-editor details').count()==2)
  check(f'{width} native template milestones loaded',page.locator('[data-pbw-proposal-payments] tr').count()==2)
  page.locator('[name=reference]').fill('REF-KEEP-1');page.locator('[aria-label="Section title"]').first.fill('Edited Scope')
  page.locator('[aria-label="Section content"]').first.fill('User edited rich content')
  page.locator('[aria-label="Percentage"]').nth(0).fill('70');page.locator('[aria-label="Percentage"]').nth(1).fill('30')
  page.locator('#pbw-proposal-draft-editor details').nth(1).get_by_role('button',name='Move up',exact=True).click();page.wait_for_timeout(350)
  check(f'{width} user reordering preserved',page.locator('[aria-label="Section title"]').first.input_value()=='Confirmation')
  check(f'{width} untaxed milestone amount shown',page.locator('.pbw-proposal-payment-amount').first.inner_text()=='700.00 SAR')
  check(f'{width} total percentage shown', '100.00%' in page.locator('[data-pbw-proposal-payment-total]').inner_text())
  page.locator('[data-sales-save]').click();page.wait_for_timeout(150)
  h=page.evaluate("calls.filter(c=>c.url.endsWith('/create')).at(-1).p.header");p=json.loads(h['proposal_payload']);(OUT/'last_payload.json').write_text(json.dumps({'header':h,'proposal':p,'errors':errors},indent=2))
  check(f'{width} proposal content included in same save',p['sections'][1]['name']=='Edited Scope' and ''.join(E.HTML(p['sections'][1]['content']).itertext())=='User edited rich content')
  check(f'{width} original reference reaches save',h['reference']=='REF-KEEP-1')
  check(f'{width} reordered sections and percentages saved',p['sections'][0]['name']=='Confirmation' and str(p['payments'][0]['percentage'])=='70')
  check(f'{width} proposal child payload excluded from pricing calls',page.evaluate("calls.filter(c=>c.url.endsWith('/preview')).every(c=>!('proposal_payload' in c.p.header))"))
  before=page.evaluate("calls.filter(c=>c.url.endsWith('proposal-template-preview')).length")
  page.locator('[data-pbw-proposal-load]').click();check(f'{width} replacing content asks confirmation',page.get_by_role('button',name='Keep draft',exact=True).is_visible());page.get_by_role('button',name='Keep draft',exact=True).click()
  check(f'{width} cancel replacement keeps content',page.evaluate("calls.filter(c=>c.url.endsWith('proposal-template-preview')).length")==before and page.locator('[aria-label="Section title"]').nth(1).input_value()=='Edited Scope')
  check(f'{width} dangerous rich HTML stripped',page.evaluate("!fixtureProposal.safeHTML('<img src=x onerror=alert(1)><script>alert(1)</script><a href=javascript:alert(1)>bad</a>').match(/onerror|javascript:|<script/i)"))
  check(f'{width} no page horizontal overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
  page.screenshot(path=str(OUT/f'proposal_draft_{width}.png'),full_page=True)
  page.locator('select[name=kind]').select_option('standard');page.locator('[data-sales-save]').click();page.wait_for_timeout(100)
  h=page.evaluate("calls.filter(c=>c.url.endsWith('/create')).at(-1).p.header")
  check(f'{width} standard save excludes technical fields',all(k not in h for k in ['proposal_payload','template_id','title','reference']))
  check(f'{width} no browser JS errors',not errors)
  page.close()
 # Saved proposal controls use their original server routes and native fields.
 for width in [1440,390]:
  page=browser.new_page(viewport={'width':width,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  section=Record(id=1,sequence=10,name='Executive Summary',section_type='executive',content='<p>Saved content</p>',include_in_report=True,page_break_before=False,_fields={'section_type':NS(selection=proposalboot['types'])})
  pay=Record(id=1,sequence=10,name='Advance',percentage=100,due_condition='On order',amount=1000.0)
  order=Record(order_line=RS([NS(display_type=False)]),id=501,name='Q00501',partner_id=p1,pbw_portal_creator_id=NS(name='Preparer'),pbw_portal_review_state='draft',pbw_order_review_state='none',pbw_portal_review_note='',user_id=NS(name='Preparer'),validity_date='2026-12-01',date_order='2026-11-08',state='draft',_fields={'state':NS(selection=[('draft','Quotation')]),'pbw_portal_review_state':NS(selection=[('draft','Draft')]),'pbw_order_review_state':NS(selection=[('none','None')])},
   absar_proposal_type='technical',absar_proposal_title='Saved title',absar_proposal_reference='Existing reference',absar_proposal_signatory='Manager',absar_proposal_signatory_title='Director',absar_proposal_customer_signatory='Buyer',absar_proposal_customer_signatory_title='CEO',absar_proposal_template_id=NS(id=10,name='Original technical template'),absar_proposal_section_ids=RS([section]),absar_proposal_payment_ids=RS([pay]),_pbw_sales_document_type=lambda:'technical',_pbw_sales_document_label=lambda:'Technical & Financial Proposal',_pbw_sales_project=lambda:empty,env={'absar.proposal.section':NS(_fields=section._fields)})
  ctx={**common,'order':order,'can_edit':True,'can_print':True,'can_confirm_direct':True,'can_approve':False,'can_approve_order':False,'can_submit':False,'can_request_order':False,'can_return':False,'line_boot_json':json.dumps({**boot,'order_id':501,'version':'saved'})}
  page.set_content(render('portal_backend_workspace.sales__sales_detail',ctx));page.evaluate(fetch);page.add_script_tag(content=js);page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))");page.add_script_tag(content=editor)
  check(f'{width} existing title and reference rendered',page.locator('[name=reference]').input_value()=='Existing reference' and page.locator('[name=title]').input_value()=='Saved title')
  check(f'{width} native template remains selected',page.locator('select[name=template_id]').input_value()=='10')
  check(f'{width} original signatory fields are editable',page.locator('[name=customer_signatory]').input_value()=='Buyer')
  form=page.locator('form#pbw-milestone-1')
  check(f'{width} saved milestone fields belong to save form',form.evaluate("f=>Object.fromEntries(new FormData(f).entries())")['name']=='Advance')
  check(f'{width} saved milestone uses scoped write route',form.get_attribute('action')=='/my/workspace/sales/501/milestone/1/save')
  check(f'{width} saved milestone amount available','1000' in page.locator('table').last.inner_text())
  page.set_content(render('portal_backend_workspace.sales__sales_detail',{**ctx,'can_edit':False,'can_confirm_direct':False}))
  check(f'{width} readonly proposal header retained','Existing reference' in page.locator('body').inner_text())
  check(f'{width} readonly proposal cannot edit milestone',page.locator('form#pbw-milestone-1').count()==0)
  check(f'{width} readonly proposal cannot load template',page.locator('form[action$="/template"]').count()==0)
  check(f'{width} no saved-page JS errors',not errors)
  page.close()
 browser.close()
(OUT/'results.json').write_text(json.dumps(results,indent=2));print(f'{len(results)} actual-script browser assertions passed (mocked HTTP/local renderer).')
