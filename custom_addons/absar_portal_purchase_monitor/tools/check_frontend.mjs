// Actual frontend functions with DOM-shaped fixtures; no browser/Odoo runtime.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source = fs.readFileSync(new URL('../static/src/js/purchase_workspace.js', import.meta.url), 'utf8');
const state = {company_id: 1, currency_id: 2, lines: [{product_qty: 1, price_unit: 5000, discount: 0, taxes_id: [3], product_uom: 4, price_subtotal: 5000}]};
const ctx = vm.createContext({state});
vm.runInContext(source.slice(source.indexOf('    const amountKey ='), source.indexOf('    const changed =')) + '\nthis.lineAmount=lineAmount; this.amountKey=amountKey;', ctx);
const line = state.lines[0];
assert.equal(ctx.lineAmount(line), 5000);
line.product_qty = 2;
assert.equal(ctx.lineAmount(line), 10000); // old cached 5000 must be ignored
line.discount = 10;
assert.equal(ctx.lineAmount(line), 9000);
line.price_subtotal = 7826.09; line._amountKey = ctx.amountKey(line);
assert.equal(ctx.lineAmount(line), 7826.09); // preserve native included-tax result
line.price_unit = 100;
assert.equal(ctx.lineAmount(line), 180);

class Element {
    constructor(tag) {this.tagName=tag; this.children=[]; this.handlers={}; this.dataset={};}
    append(...nodes) {this.children.push(...nodes);}
    replaceChildren(...nodes) {this.children=nodes;}
    addEventListener(name, handler) {this.handlers[name]=handler;}
    setAttribute(name, value) {this[name]=value;}
    close() {this.closed=true;}
}
const text = (tag, value) => Object.assign(new Element(tag), {textContent:value});
// Values must enter the save state while typing, before blur or a server rerender.
let committed = '', changes = 0;
const inputContext = vm.createContext({document:{createElement:tag=>new Element(tag)}, readonly:false,
    changed:()=>changes++});
vm.runInContext(source.slice(source.indexOf('    function input('), source.indexOf('    function button('))+'\nthis.input=input;', inputContext);
const reference = inputContext.input('', 'text', value=>{committed=value;});
reference.value = 'QA reference'; reference.handlers.input();
assert.equal(committed, 'QA reference'); assert.equal(changes, 1);
reference.handlers.change(); assert.equal(changes, 1); // blur must not recalculate twice
const host = new Element('div');
Object.assign(ctx, {byId:()=>host, text, totals:null, totalsPending:true, labels:{currency_id:{label:'SAR'}}, money:value=>Number(value).toFixed(2)});
vm.runInContext(source.slice(source.indexOf('    function renderTotals()'), source.indexOf('    async function recalculate()'))+'\nthis.renderTotals=renderTotals;',ctx);
ctx.renderTotals();
assert.equal(host.children.filter(node=>node.tagName==='p').length,3);
assert.equal(host.children[2].children[0].textContent,'Calculating…');
ctx.totals={untaxed:5000,tax:750,total:5750,currency:'SAR'};
ctx.renderTotals();
assert.equal(host.children[2].children[0].textContent,'5750.00');
assert.equal(host['aria-busy'],'true');
ctx.totalsPending=false; ctx.renderTotals();
assert.equal(host.children[1].children[0].textContent,'750.00');

globalThis.document={createElement:tag=>new Element(tag)};
const productSource=fs.readFileSync(new URL('../static/src/js/purchase_product_form.js',import.meta.url),'utf8');
const {openPurchaseProductDialog}=await import('data:text/javascript;base64,'+Buffer.from(productSource).toString('base64'));
const fields=new Map(), lookups=new Map(), buttons=new Map(), dialog=new Element('dialog');
let payload, created=0;
await openPurchaseProductDialog({
    post:async(path,data)=>{
        if(path==='/product-defaults')return {categ_id:{id:1,label:'All'},uom_id:{id:2,label:'Unit'},uom_po_id:{id:2,label:'Unit'},purchase_method:'receive',supplier_taxes:[{id:3,label:'Tax15%'}]};
        assert.equal(path,'/product-create');payload=structuredClone(data);return {id:9,label:'Test'};
    },
    modal:()=>({dialog,body:new Element('div'),foot:new Element('div')}),
    field:(label,node)=>{fields.set(label,node);},
    input:(value,type,change)=>({value,change}),
    lookup:(kind,selected,select)=>{const result={kind,select};lookups.set(kind,result);return result;},
    button:(label,callback)=>{const node={callback};buttons.set(label,node);return node;},
    text, companyId:7, onCreate:async()=>{created++;}
});
const save=buttons.get('Create and Add');
await save.callback(); assert.equal(payload,undefined); // required name blocks creation
fields.get('Product Name *').change('Test Product');
lookups.get('tax').select({id:3,label:'Tax15%'});
lookups.get('account').select({id:6,label:'Expense'});
await save.callback();
assert.deepEqual(payload.supplier_taxes_id,[3]);
assert.equal(payload.categ_id,1);assert.equal(payload.uom_id,2);assert.equal(payload.uom_po_id,2);
assert.equal(payload.property_account_expense_id,6);assert.equal(payload.company_id,7);
assert.equal(created,1);assert.equal(dialog.closed,true);
console.log('PASS: changed amount cache, persistent totals panel/pending state, product validation/payload and tax deduplication (frontend fixtures).');
