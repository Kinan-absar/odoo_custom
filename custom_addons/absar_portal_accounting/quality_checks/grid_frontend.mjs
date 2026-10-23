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
    addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
    removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x!==fn);}
    dispatchEvent(e){e.target ||= this;for(const fn of this.listeners[e.type]||[])fn(e);if(!e.stopped&&this.parentElement)this.parentElement.dispatchEvent(e);return !e.defaultPrevented;}
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
const root=new Node('section');document={createElement:t=>new Node(t),activeElement:null,readyState:'complete',getElementById:()=>root};
const body=new Node('body');body.append(root);document.body=body;
const window={innerWidth:1200,innerHeight:700,addEventListener(){},removeEventListener(){}};
Object.assign(globalThis,{document,window});
const boot={default_taxes:[{id:15,name:'VAT 15%'}],company_id:1,company_currency_name:'SAR',analytic_names:{'5':'PHC Project'},kind:'bills',name:'New',state:'draft',editable:true,review_required:true,review:'draft',roles:{preparer:true},selections:{},
    currency_id:1,journal_id:2,partner_id:3,lines:[{product_id:9,product_name:'Cement',name:'Negotiated description',quantity:4,price_unit:23,discount:2,account_id:8,account_name:'Materials',product_uom_id:1,uom_name:'Unit',taxes_id:[15],tax_names:[{id:15,name:'VAT'}],analytic_distribution:{'5':100}}]};
root.dataset={boot:JSON.stringify(boot),csrf:'test'};
const calls=[];let resolveOptions;
const product={id:9,name:'Cement revised',type:'consu',is_storable:false,can_edit:true,shared:true,version:'p1',categ_id:{id:1,name:'Materials'},uom_id:{id:1,name:'Unit'},uom_po_id:{id:1,name:'Unit'},property_account_expense_id:{id:8,name:'Materials'},purchase_method:'receive',supplier_taxes:[{id:15,name:'VAT'}],standard_price:10};
let deferOptions=false;
const ctx=vm.createContext({document,window,Event:class{constructor(type){this.type=type;}},URLSearchParams,history:{replaceState(){}},console,
 setTimeout:fn=>1,clearTimeout(){},fetch:async(url,options)=>{
  const payload=JSON.parse(options.body.get('payload'));calls.push({url,payload});assert.equal(options.body.get('csrf_token'),'test');
  let result;if(url.endsWith('/options')){if(deferOptions)await new Promise(r=>{resolveOptions=r;});result=[{id:9,name:'Selected Product',account_id:8,account_name:'Expense',product_uom_id:1,uom_name:'Unit',tax_ids:[]}];}
  else if(url.endsWith('/product-read')||url.endsWith('/product-defaults'))result=product;
  else if(url.endsWith('/product-update')||url.endsWith('/product-create'))result={id:9,name:payload.name,account_id:8,account_name:'New Expense',product_uom_id:1,uom_name:'Unit',tax_ids:[],product_updated:url.endsWith('/product-update')};
  else throw new Error('Unexpected '+url);
  return {json:async()=>({ok:true,result})};}});
let source=fs.readFileSync(new URL('../static/src/accounting.js',import.meta.url),'utf8').replace(/^import .*$/gm,'');
const navigation=fs.readFileSync(new URL('../static/src/draft_navigation.js',import.meta.url),'utf8').replace(/^export /gm,'');
const shared=['line_grid.js','purchase_ui.js','analytic_editor.js'].map(name=>fs.readFileSync(new URL('../static/src/'+name,import.meta.url),'utf8').replace(/^export /gm,'')).join('\n');
source=source.replace("        state.payment_method ||=", "        root.test={moveGrid,render,productForm,selectProduct,get state(){return state;}};\n        state.payment_method ||=");
vm.runInContext(navigation+shared+source,ctx);
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const key=async(node,key,shiftKey=false)=>{node.dispatchEvent({type:'keydown',key,shiftKey,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;}});await settle();};
assert.deepEqual(root.querySelectorAll('thead th').map(n=>n.textContent),['Product','Account','Analytic','Quantity','Price','Disc.%','Taxes','Amount','Company Currency','']);
assert(root.textContent.includes('PHC Project'));assert(root.textContent.includes('SAR'));
assert.equal(root.querySelectorAll('[data-grid-row]').length,1);
assert.equal(root.querySelectorAll('.aca-line-detail-row').length,0);
assert.equal(root.querySelectorAll('[data-grid-entry]').length,7);
let quantity=root.querySelector('[data-grid-column="3"] input');quantity.focus();quantity.value='12';quantity.dispatchEvent({type:'input'});
root.test.render();quantity=root.querySelector('[data-grid-column="3"] input');assert.equal(document.activeElement,quantity);assert.equal(Number(quantity.value),12);
await key(quantity,'Enter');assert.equal(document.activeElement.closest('td').dataset.gridColumn,'4');
await key(document.activeElement,'Enter',true);assert.equal(document.activeElement.closest('td').dataset.gridColumn,'3');
root.test.moveGrid(0,6,1);assert.equal(root.test.state.lines.length,2);assert.deepEqual([...root.test.state.lines[1].taxes_id],[15]);assert.equal(document.activeElement.closest('[data-grid-row]').dataset.gridRow,'1');
// Enter waits for pending product search/selection, then advances into Account.
deferOptions=true;const lookup=root.querySelector('[data-grid-row="0"] [data-grid-column="0"] input');lookup.focus();
await settle();const pending=key(lookup,'Enter');assert.equal(root.test.state.lines[0].product_name,'Cement');
resolveOptions();await pending;await settle();assert.equal(root.test.state.lines[0].product_name,'Selected Product');assert.deepEqual([...root.test.state.lines[0].taxes_id],[15]);
assert.equal(document.activeElement.closest('td').dataset.gridColumn,'1');
deferOptions=false;
// Opening an existing product exposes Expense Account and preserves negotiated line values.
const line=root.test.state.lines[0];line.name='Negotiated';line.price_unit=23;line.quantity=12;line.taxes_id=[15];
await root.test.productForm(9,'',selected=>root.test.selectProduct(line,selected));await settle();
const dialog=body.querySelector('[role="dialog"]');assert(dialog.textContent.includes('Expense Account'));assert(dialog.textContent.includes('Bill Control Policy'));
const productName=dialog.querySelector('[aria-label="name"]');productName.value='Edited Cement';productName.dispatchEvent({type:'input'});
dialog.querySelectorAll('button').find(n=>n.textContent==='Save Product').click();await settle();
assert.equal(line.product_name,'Edited Cement');assert.equal(line.name,'Negotiated');assert.equal(line.price_unit,23);assert.equal(line.quantity,12);assert.deepEqual([...line.taxes_id],[15]);
assert.equal(calls.findLast(c=>c.url.endsWith('/product-update')).payload.version,'p1');assert.equal(calls.findLast(c=>c.url.endsWith('/product-update')).payload.property_account_expense_id,8);
// Create and Edit is offered directly in the product dropdown.
const productSearch=root.querySelector('[data-grid-row="0"] [data-grid-column="0"] input');productSearch.focus();await settle();
assert(root.textContent.includes('Create and Edit…'));
// Escaping closes the lookup and late requests cannot reopen it.
deferOptions=true;productSearch.value='late';productSearch.dispatchEvent({type:'input'});
const lateEnter=key(productSearch,'Enter');await settle();
await key(productSearch,'Escape');resolveOptions();await lateEnter;await settle();
assert.equal(productSearch.getAttribute('aria-expanded'),'false');
root.test.state.kind='journals';root.test.state.lines=[{name:'Accrual',account_id:8,account_name:'Expense',partner_id:3,partner_name:'Vendor',debit:100,credit:0,analytic_distribution:{}}];
root.test.render();assert.deepEqual(root.querySelectorAll('thead th').map(n=>n.textContent),['Account','Partner','Label','Analytic Distribution','Taxes','Debit','Credit','Tax Grids','']);assert.equal(root.querySelectorAll('[data-grid-row]').length,1);assert.equal(root.querySelectorAll('[data-grid-entry]').length,8);
const debit=root.querySelector('[data-grid-column="5"] input');debit.focus();debit.value='150';debit.dispatchEvent({type:'input'});
await key(debit,'Enter');assert.equal(document.activeElement.closest('td').dataset.gridColumn,'6');
assert.equal(root.test.state.lines[0].debit,150);
root.test.state.editable=false;root.test.render();assert(root.querySelectorAll('.aca-grid-lines input').every(n=>n.disabled));

console.log('PASS: compact single rows, matching native invoice/journal columns, typing/focus preservation, Enter/Shift+Enter, new row at end, Enter waits for async product search, product form expense account, versioned update preserves negotiated line data, Create and Edit option, Escape closes dropdown (DOM fixtures).');
root.test.state.kind='bills';root.test.state.journal_items=[{account:'Expense',partner:'Vendor',name:'Materials',analytic_distribution:{'5':100},tax_names:[{id:15,name:'VAT 15%'}],grid_names:[{id:4,name:'Tax Grid'}],debit:100,credit:0}];
root.test.render();root.querySelectorAll('[role="tab"]').find(n=>n.textContent==='Journal Items').click();
assert.deepEqual(root.querySelectorAll('thead th').map(n=>n.textContent),['Account','Partner','Label','Analytic Distribution','Taxes','Debit','Credit','Tax Grids']);
assert(root.textContent.includes('PHC Project'));assert(root.textContent.includes('VAT 15%'));assert(root.textContent.includes('Tax Grid'));
console.log('PASS: saved bill Journal Items tab uses all eight matching native columns with analytic, tax and grid values.');
// Screenshot regression: full account name, aligned percentage, no edit controls on readonly records.
const longAnalytic='MEP Jussur Emdad HR - Najm Qantera Company / PHC Site Operations';
root.test.state.kind='journals';root.test.state.analytic_names={'5':longAnalytic};
root.test.state.lines[0].analytic_distribution={'5':100};root.test.render();
root.querySelector('.aca-analytic-control').click();
let analyticDialog=body.querySelector('.apw-dialog');
assert.equal(analyticDialog.querySelector('.apw-chip').textContent,longAnalytic);
assert.equal(Number(analyticDialog.querySelector('[aria-label="Allocation percentage"]').value),100);
assert(analyticDialog.querySelectorAll('input').every(n=>n.disabled));
assert(!analyticDialog.querySelectorAll('button').some(n=>n.textContent==='Apply'));
analyticDialog.querySelectorAll('button').find(n=>n.textContent==='Close').click();
assert(!body.querySelector('.apw-dialog'));
// Editable drafts retain selection and percentage editing, with the full selected name below the picker.
root.test.state.editable=true;root.test.render();root.querySelector('.aca-analytic-control').click();
analyticDialog=body.querySelector('.apw-dialog');
assert.equal(analyticDialog.querySelector('.apw-chip').textContent.replace('×',''),longAnalytic);
const percentage=analyticDialog.querySelector('[aria-label="Allocation percentage"]');percentage.value='25';percentage.dispatchEvent({type:'input'});
analyticDialog.querySelectorAll('button').find(n=>n.textContent==='Apply').click();
assert(analyticDialog.textContent.includes('Each used plan must total 100%.'));
percentage.value='100';percentage.dispatchEvent({type:'input'});analyticDialog.querySelectorAll('button').find(n=>n.textContent==='Apply').click();
assert.equal(root.test.state.lines[0].analytic_distribution['5'],100);
assert(!body.querySelector('.apw-dialog'));
console.log('PASS: analytic dialog shows full readonly name and percentage without edit controls; editable draft displays full selected name and applies percentage to the same account.');
