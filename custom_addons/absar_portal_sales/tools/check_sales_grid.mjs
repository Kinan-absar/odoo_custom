import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
let document;
const toKey = name => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
class Node {
    constructor(tag) {this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.attrs={};this.listeners={};this.className='';this.hidden=false;this._text='';this.value='';this.selectionStart=0;this.selectionEnd=0;}
    get classList(){return {contains:name=>this.className.split(' ').includes(name),add:name=>{this.className+=' '+name;}};}
    set textContent(value){this._text=String(value??'');this.children=[];}
    get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
    append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
    replaceChildren(...nodes){for(const n of this.children)n.parentElement=null;this._text='';this.children=[];this.append(...nodes);}
    addEventListener(name,fn,capture=false){(this.listeners[name]||=[]).push({fn,capture});}
    removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x.fn!==fn);}
    dispatchEvent(e){e.target ||= this;const path=[];for(let n=this;n;n=n.parentElement)path.push(n);
      for(const n of [...path].reverse()){for(const h of n.listeners[e.type]||[])if(h.capture&&!e.stopped)h.fn(e);}
      for(const n of path){for(const h of n.listeners[e.type]||[])if(!h.capture&&!e.stopped)h.fn(e);}
      return !e.defaultPrevented;}
    setAttribute(k,v){this.attrs[k]=String(v);if(['disabled','hidden','type','role'].includes(k))this[k]=v;if(k.startsWith('data-'))this.dataset[toKey(k.slice(5))]=String(v);}
    getAttribute(k){if(k.startsWith('data-'))return this.dataset[toKey(k.slice(5))]??null;return this.attrs[k]??null;}
    matches(selector){return selector.split(',').some(s=>{s=s.trim();if(s===':popover-open')return this.popoverOpen;const cls=s.match(/\.([\w-]+)/);if(cls&&!this.classList.contains(cls[1]))return false;const tag=s.match(/^[\w-]+/);if(tag&&tag[0].toUpperCase()!==this.tagName)return false;for(const a of s.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)){const v=this.getAttribute(a[1]);if(v===null||(a[2]!==undefined&&v!==a[2]))return false;}return true;});}
    closest(s){for(let n=this;n;n=n.parentElement)if(n.matches(s))return n;return null;}
    querySelectorAll(selector){const parts=selector.split(/\s+(?![^\[]*\])/);const all=[];const walk=n=>{for(const c of n.children){let ok=c.matches(parts.at(-1));let parent=c.parentElement;for(let i=parts.length-2;i>=0&&ok;i--){while(parent&&!parent.matches(parts[i]))parent=parent.parentElement;if(!parent)ok=false;else parent=parent.parentElement;}if(ok)all.push(c);walk(c);}};walk(this);return all;}
    querySelector(s){return this.querySelectorAll(s)[0]||null;}
    contains(n){return n===this||this.children.some(c=>c.contains(n));}
    focus(){if(document.activeElement===this)return;document.activeElement=this;this.dispatchEvent({type:'focus'});}
    select(){this.selected=true;}
    setSelectionRange(a,b){this.selectionStart=a;this.selectionEnd=b;}
    scrollIntoView(){}
    getBoundingClientRect(){return {left:950,top:610,bottom:640,width:160};}
    get scrollHeight(){return this.children.length*32;}
    get isConnected(){return Boolean(this.parentElement)||this===root;}
    showPopover(){this.popoverOpen=true;}
    hidePopover(){this.popoverOpen=false;}
    click(){this.dispatchEvent({type:'click'});}
    remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.parentElement=null;}
    showModal(){this.open=true;}
    close(){this.open=false;this.dispatchEvent({type:'close'});}
}
let headerRoot=null;const root=new Node('section');document={createElement:t=>new Node(t),activeElement:null,readyState:'loading',getElementById:id=>id==='aps-line-editor'?root:id==='aps-new-details'?headerRoot:null,addEventListener(){},querySelector:s=>body.querySelector(s)};
const body=new Node('body');body.append(root);document.body=body;
const redirects=[];const window={location:{assign:path=>redirects.push(path)},innerWidth:1200,innerHeight:700,addEventListener(){},removeEventListener(){}};
Object.assign(globalThis,{document,window});
const boot={order_id:5,company_id:7,version:'v1',editable:true,currency:'SAR',untaxed:20,tax:3,total:23,
 analytic_labels:{10:{id:10,label:'PHC Building / Long Project Name',plan:'Projects',plan_id:100}},
 lines:[{id:1,product_id:2,product:{id:2,label:'Product A'},name:'Negotiated label',uom_id:1,uom:{id:1,label:'Unit'},quantity:2,price_unit:10,discount:0,taxes_id:[15],taxes:[{id:15,label:'VAT 15%'}],analytic_distribution:{10:100},subtotal:20}]};
root.dataset={boot:JSON.stringify(boot),csrf:'csrf'};
const calls=[];let waitDefaults=false,resolveDefaults;
const ctx=vm.createContext({document,window,Event:class{constructor(type){this.type=type;}},URLSearchParams,console,setTimeout:()=>1,clearTimeout(){},
 fetch:async(url,opts)=>{const data=JSON.parse(opts.body.get('payload'));calls.push({url,data});assert.equal(opts.body.get('csrf_token'),'csrf');let result;
  if(url.endsWith('/lookup'))result={items:[{id:99,label:'Selected '+data.kind,plan_id:100,plan:'Projects'}],more:false};
  else if(url.endsWith('/defaults')){if(waitDefaults)await new Promise(r=>{resolveDefaults=r;});result={id:0,product_id:99,product:{id:99,label:'Selected product'},name:'Native description',quantity:2,uom_id:1,uom:{id:1,label:'Unit'},price_unit:33,discount:0,taxes_id:[15],taxes:[{id:15,label:'VAT 15%'}],analytic_distribution:{},subtotal:66};}
  else if(url.endsWith('/create'))result={...boot,order_id:55,redirect:'/my/employee/sales/55'};
  else if(url.endsWith('/save'))result={...boot,lines:data.lines,version:'v2'};
  else if(url.endsWith('/preview'))result={untaxed:66,tax:9.9,total:75.9,line_amounts:data.lines.map(()=>66)};
  else throw new Error('Unexpected '+url);
  return {json:async()=>({ok:true,result})};}});
const prefix=['purchase_ui.js','analytic_editor.js','sales_lines.js'].map(n=>fs.readFileSync(new URL('../static/src/js/'+n,import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/^export /gm,'')).join('\n');
vm.runInContext(prefix+'\nthis.editor=mountSalesLines(document.getElementById("aps-line-editor"));',ctx);
const editor=ctx.editor;
const settle=async()=>{for(let i=0;i<15;i++)await Promise.resolve();};
const key=async(node,key,shiftKey=false)=>{node.dispatchEvent({type:'keydown',key,shiftKey,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;}});await settle();};
assert.deepEqual(root.querySelectorAll('thead th').map(n=>n.textContent),['Product','Analytic Distribution','Quantity','UoM','Unit Price','Taxes','Disc.%','Amount','']);
assert.equal(root.querySelectorAll('[data-sales-entry]').length,7);
let qty=root.querySelector('[data-sales-column="2"] input');qty.focus();qty.value='4';qty.dispatchEvent({type:'input'});editor.render();
assert.equal(Number(document.activeElement.value),4);assert.equal(document.activeElement.closest('td').dataset.salesColumn,'2');
await key(document.activeElement,'Enter');assert.equal(document.activeElement.closest('td').dataset.salesColumn,'3');
await key(document.activeElement,'Enter',true);assert.equal(document.activeElement.closest('td').dataset.salesColumn,'2');
// Purchase lookup waits for native product defaults; the grid does not advance twice.
const lookup=root.querySelector('[data-sales-column="0"] input');lookup.focus();await settle();waitDefaults=true;
lookup.value='New';lookup.dispatchEvent({type:'input'});lookup.dispatchEvent({type:'focus'});await settle();
await key(lookup,'Enter');assert.equal(document.activeElement,lookup);resolveDefaults();await settle();
assert.equal(editor.state.lines[0].product_id,99);assert.equal(editor.state.lines[0].price_unit,33);
assert.equal(document.activeElement.closest('td').dataset.salesColumn,'1');
assert.equal(editor.state.lines[0].analytic_distribution['10'],100);
// Product property edits preserve agreed price, quantity, description and taxes.
const before=editor.state.lines[0];before.name='Negotiated';before.price_unit=29;before.quantity=4;
await editor.selectProduct(before,{id:99,label:'Renamed product',product_updated:true});
assert.equal(before.price_unit,29);assert.equal(before.quantity,4);assert.equal(before.name,'Negotiated');assert.deepEqual([...before.taxes_id],[15]);
root.querySelector('.aps-sales-analytic').click();let dialog=body.querySelector('.apw-dialog');
assert(dialog.textContent.includes('Use')||dialog.textContent.includes('Allocate each plan to 100%'));
assert(dialog.textContent.includes('PHC Building / Long Project Name'));
assert(dialog.querySelectorAll('button').some(n=>n.textContent==='Clear distribution'));
dialog.querySelectorAll('button').find(n=>n.textContent==='Close').click();
await editor.preview();assert(root.textContent.includes('75.90'));
await editor.save();assert.equal(calls.findLast(c=>c.url.endsWith('/save')).data.version,'v1');assert.equal(editor.state.version,'v2');
editor.moveGrid(0,6,1);assert.equal(editor.state.lines.length,2);assert.equal(document.activeElement.closest('[data-sales-row]').dataset.salesRow,'1');
editor.state.editable=false;editor.render();assert(!root.textContent.includes('Save Lines'));assert(root.querySelectorAll('input').every(n=>n.disabled));
console.log('PASS: actual Sales grid exact backend columns, typing/focus, Enter/Shift+Enter including lookup, async product defaults before navigation, negotiated data preservation on product edits, Purchase analytic editor, native preview response, CSRF/versioned save, next row, readonly controls (DOM fixtures).');
vm.runInContext(`this.sharedResult=null;openAnalyticDistribution({ui:createPurchaseUI({root:document.getElementById('aps-line-editor'),post:async()=>({items:[]}),companyId:7}),distribution:{'10,12':100},labels:{10:{id:10,label:'PHC',plan:'Projects',plan_id:100},12:{id:12,label:'MEP',plan:'Departments',plan_id:200}},onApply:(distribution,labels)=>{this.sharedResult={distribution,labels};}});`,ctx);
dialog=body.querySelector('.apw-dialog');assert.equal(dialog.querySelectorAll('.apw-chip').length,2);dialog.querySelectorAll('button').find(n=>n.textContent==='Apply').click();
assert.equal(ctx.sharedResult.distribution['10,12'],100);assert.equal(ctx.sharedResult.labels['12'].plan_id,200);
console.log('PASS: shared Purchase allocation editor preserves two accounts from different plans in one 100% row.');

// New quotations expose the same grid immediately and save details + lines once.
headerRoot=new Node('div');for(const [name,value] of Object.entries({partner_id:'21',project_id:'31',kind:'standard',validity_date:'2026-11-01'})){const input=new Node('input');input.setAttribute('name',name);input.value=value;headerRoot.append(input);}
body.append(headerRoot);root.dataset.boot=JSON.stringify({...boot,order_id:0,version:'',lines:[{...boot.lines[0],id:0}]});
vm.runInContext('this.newEditor=mountSalesLines(document.getElementById("aps-line-editor"));',ctx);
assert(root.textContent.includes('Save Quotation'));await Promise.all([ctx.newEditor.save(),ctx.newEditor.save()]);
const creates=calls.filter(c=>c.url.endsWith('/new-api/create'));assert.equal(creates.length,1);
assert.equal(creates[0].data.header.partner_id,'21');assert.equal(creates[0].data.header.project_id,'31');assert.equal(creates[0].data.lines[0].id,0);
assert.deepEqual(redirects,['/my/employee/sales/55']);
console.log('PASS: new quotation starts with the same grid, sends details and lines with CSRF, blocks duplicate saves and opens its saved form (DOM fixtures).');
