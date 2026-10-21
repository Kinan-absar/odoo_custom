// Actual portal UI modules and grid methods on a minimal DOM fixture. No browser/Odoo runtime.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const path = name => new URL('../static/src/js/' + name, import.meta.url);
let document;
const toKey = name => name.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
class Node {
    constructor(tag) {this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.attrs={};this.listeners={};this.className='';this.hidden=false;this._text='';this.value='';this.selectionStart=0;this.selectionEnd=0;}
    get classList(){return {contains:name=>this.className.split(' ').includes(name),add:name=>{this.className+=' '+name;}};}
    set textContent(value){this._text=String(value??'');this.children=[];}
    get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
    append(...nodes){for(const n of nodes){n.parentElement=this;this.children.push(n);}}
    replaceChildren(...nodes){for(const n of this.children)n.parentElement=null;this._text='';this.children=[];this.append(...nodes);}
    addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
    removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x!==fn);}
    dispatchEvent(e){e.target ||= this;for(const fn of this.listeners[e.type]||[])fn(e);return !e.defaultPrevented;}
    setAttribute(k,v){this.attrs[k]=String(v);if(k.startsWith('data-'))this.dataset[toKey(k.slice(5))]=String(v);}
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
const root=new Node('section');document={createElement:t=>new Node(t),activeElement:null};
const window={innerWidth:1200,innerHeight:700,addEventListener(){},removeEventListener(){}};
Object.assign(globalThis,{document,window});
const moduleText=fs.readFileSync(path('purchase_ui.js'),'utf8');
const {createPurchaseUI,positionPurchaseOptions}=await import('data:text/javascript;base64,'+Buffer.from(moduleText).toString('base64'));
for(const [width,height,rect] of [[1200,700,{left:1150,top:610,bottom:640,width:160}],[360,640,{left:12,top:60,bottom:90,width:200}],[360,640,{left:12,top:580,bottom:610,width:200}]]){
 const p=positionPurchaseOptions(rect,width,height);assert(p.left>=8&&p.left+p.width<=width-8);assert(p.top>=8&&p.top+p.height<=height);assert(p.height<=280);
}
let selected=[],advanced=0,resolveSelection;
const ui=createPurchaseUI({root,companyId:7,post:async()=>({items:[{id:9,label:'Test Product'}]})});
const wrap=ui.lookup('product',null,async item=>{selected.push(item);await new Promise(r=>{resolveSelection=r;});},{}, {advance:()=>advanced++,productForm:async()=>{}});root.append(wrap);
const box=wrap.querySelector('input');box.focus();await Promise.resolve();await Promise.resolve();
assert.equal(box.getAttribute('aria-expanded'),'true');
const options=wrap.querySelector('.apw-options');assert(options.textContent.includes('Create and Edit…'));
const e={type:'keydown',key:'Enter',preventDefault(){this.defaultPrevented=true;}};box.dispatchEvent(e);
assert.equal(selected[0].id,9);assert.equal(advanced,0);resolveSelection();await Promise.resolve();await Promise.resolve();assert.equal(advanced,1);
assert.equal(box.getAttribute('aria-expanded'),'false');
// A response received after focus is lost must not reopen its dropdown.
let resolveSearch;
const deferred=createPurchaseUI({root,companyId:7,post:()=>new Promise(r=>{resolveSearch=r;})});
const pending=deferred.lookup('product',null,()=>{});root.append(pending);pending.querySelector('input').focus();pending.dispatchEvent({type:'apw-dispose'});resolveSearch({items:[{id:1,label:'Stale'}]});await Promise.resolve();await Promise.resolve();assert(pending.querySelector('.apw-options').hidden);
const source=fs.readFileSync(path('purchase_workspace.js'),'utf8');
const host=new Node('tbody');root.append(host);const state={lines:[{id:1,product_id:9,product_label:'Test',product_qty:2,price_unit:33,discount:0,product_uom:1,uom_label:'Unit',taxes:[],taxes_id:[],name:'Keep description',analytic_distribution:{}}]};
const simpleLookup=()=>{const div=new Node('div');div.className='apw-lookup';div.append(new Node('input'));return div;};
const ctx=vm.createContext({document,window,Event:class{constructor(type){this.type=type;}},state,readonly:false,
 byId:()=>host,lookup:simpleLookup,productForm(){},money:v=>String(v),lineAmount:l=>l.product_qty*l.price_unit,
 text:(t,v,c='')=>{const n=new Node(t);n.textContent=v;n.className=c;return n;},changed(){},lineDetails(){},
 analyticDialog(){},defaultsFor(){},reprice(){},selectLineProduct(){},moveLine(){}});
for(const [start,end] of [['    function input(','    function button('],['    function button(','    function lookup('],['    function renderLines()','    byId(\'apw-lines\').addEventListener']])vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)),ctx);
vm.runInContext('this.renderLines=renderLines;this.moveGrid=moveGrid;',ctx);ctx.renderLines();
assert.equal(host.children.length,1);assert.equal(host.querySelectorAll('[data-grid-entry]').length,7);assert(!host.textContent.includes('Expense Account'));
const qty=host.querySelector('[data-grid-column="2"] input');qty.focus();qty.value='27';qty.dispatchEvent({type:'input'});assert.equal(state.lines[0].product_qty,27);
ctx.renderLines();assert.equal(document.activeElement.closest('td').dataset.gridColumn,'2');assert.equal(document.activeElement.value,27);
ctx.moveGrid(0,2,1);assert.equal(document.activeElement.closest('td').dataset.gridColumn,'3');
ctx.moveGrid(0,3,-1);assert.equal(document.activeElement.closest('td').dataset.gridColumn,'2');
// Editing product properties must leave line amounts and text intact.
const editCtx=vm.createContext({readonly:false,state,changed(){},renderLines(){}});
vm.runInContext(source.slice(source.indexOf('    async function selectLineProduct('),source.indexOf('    async function defaultsFor('))+'this.select=selectLineProduct;',editCtx);
await editCtx.select(state.lines[0],{id:9,label:'Renamed',product_updated:true,default_account:'Expense'});
assert.equal(state.lines[0].price_unit,33);assert.equal(state.lines[0].product_qty,27);assert.equal(state.lines[0].name,'Keep description');assert.equal(state.lines[0].default_account,'Expense');
console.log('PASS: bounded dropdown placement, Create and Edit option, Enter waits for selection/defaults, stale response ignored, one compact row per line, seven navigation columns, typed values and focus survive redraw, forward/back navigation, expense-account edit preserves negotiated PO data (DOM fixtures).');
vm.runInContext(source.slice(source.indexOf('    function blankLine('),source.indexOf('    async function selectLineProduct(')),ctx);
vm.runInContext(source.slice(source.indexOf("    byId('apw-lines').addEventListener('keydown'"),source.indexOf('    function lineDetails(')),ctx);
let prevented=false;
host.dispatchEvent({type:'keydown',target:document.activeElement,key:'Enter',preventDefault(){this.defaultPrevented=true;prevented=true;}});
assert(prevented);assert.equal(document.activeElement.closest('td').dataset.gridColumn,'3');
ctx.moveGrid(0,6,1);assert.equal(state.lines.length,2);assert.equal(document.activeElement.closest('[data-grid-row]').dataset.gridRow,'1');assert.equal(document.activeElement.closest('td').dataset.gridColumn,'0');
console.log('PASS: actual Enter key handler and automatic next-row creation.');
// Receipt UI: empty inputs never validate, partial quantities are sent exactly,
// and the PO refresh callback runs only after the receipt endpoint succeeds.
const receiptSource=fs.readFileSync(path('purchase_receipt.js'),'utf8');
const {openPurchaseReceiptDialog}=await import('data:text/javascript;base64,'+Buffer.from(receiptSource).toString('base64'));
let receivedPayload,doneResult;
const receiptPost=async(url,payload)=>{
 if(url==='/10/receipts')return {receipts:[{id:5,name:'WH/IN/QA',version:'r1',backorder_policy:'ask',lines:[
  {id:1,product:'Material 1',expected:5,already_received:0,uom:'Unit',lot_ready:true},
  {id:2,product:'Material 2',expected:3,already_received:0,uom:'Unit',lot_ready:true}]}]};
 assert.equal(url,'/10/receive');receivedPayload=payload;return {url:'/my/employee/purchase/10',state:'done'};
};
await openPurchaseReceiptDialog({post:receiptPost,poId:10,ui:createPurchaseUI({root,post:receiptPost,companyId:7}),onDone:r=>{doneResult=r;}});
const receiptDialog=root.querySelectorAll('dialog').at(-1);
const validate=receiptDialog.querySelectorAll('button').find(n=>n.textContent==='Validate Receipt');
await validate.listeners.click[0]();assert.equal(receivedPayload,undefined);assert(receiptDialog.textContent.includes('at least one'));
receiptDialog.querySelectorAll('button').find(n=>n.textContent==='Set Remaining Quantities').click();
const quantities=receiptDialog.querySelectorAll('input');quantities[0].value='2';quantities[0].dispatchEvent({type:'input'});quantities[1].value='0';quantities[1].dispatchEvent({type:'input'});
await validate.listeners.click[0]();assert.deepEqual(receivedPayload,{receipt_id:5,version:'r1',quantities:[{id:1,quantity:2},{id:2,quantity:0}]});assert.equal(doneResult.state,'done');assert(!receiptDialog.open);
console.log('PASS: receipt dialog requires positive quantities, sends exact partial quantities/version/receipt ID, and refreshes the PO after successful validation (DOM fixtures).');
