import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../static/src/accounting.js', import.meta.url),'utf8');
class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.handlers={};this.dataset={};this.disabled=false;this.isConnected=true;this.value='';}
    append(...children){this.children.push(...children);}
    replaceChildren(...children){this.children=children;}
    addEventListener(name,fn){this.handlers[name]=fn;}
    setAttribute(name,value){this[name]=value;if(name.startsWith('data-'))this.dataset[name.slice(5)]=value;}
    getAttribute(name){return this[name];}
    remove(){this.isConnected=false;}
    focus(){}
    querySelectorAll(selector){return walk(this).filter(n=>selector==='button'?n.tagName==='button':selector==='[data-totals]'?'totals'in n.dataset:selector==='[data-line-amount]'?n['data-line-amount']!==undefined:false);}
    querySelector(selector){return this.querySelectorAll(selector)[0];}
}
function walk(node){return [node,...node.children.flatMap(child=>typeof child==='object'?walk(child):[])];}
function find(root,label){return walk(root).find(n=>n.textContent===label);}
const fixture={id:0,company_id:1,kind:'bills',name:'New',date:'2026-10-19',invoice_date:'2026-10-19',
    currency_id:1,currency_name:'SAR',partner_id:7,journal_id:3,version:'test-version',state:'draft',review:'draft',
    roles:{preparer:true,approver:false,monitor:false},editable:true,can_review:false,selections:{},
    lines:[{name:'Materials',account_id:8,quantity:1,price_unit:0,taxes_id:[15],tax_names:[{id:15,name:'VAT 15%'}]}],
    bill_ids:[],invoice_ids:[],purchase_order_ids:[],untaxed:0,tax:0,total:0};
function mount(boot){
    const root=new Element('div'),body=new Element('body'),calls=[];let timer;
    root.dataset={boot:JSON.stringify(boot),csrf:'csrf-fixture'};body.append(root);
    const document={readyState:'complete',body,createElement:tag=>new Element(tag),getElementById:()=>root};
    const context=vm.createContext({document,URLSearchParams,console,history:{replaceState(){}},
        setTimeout:fn=>{timer=fn;return 1;},clearTimeout(){timer=null;},window:{confirm:()=>true,prompt:()=>null,location:{assign(){}}},
        fetch:async(url,options)=>{const data=JSON.parse(options.body.get('payload'));calls.push({url,data});
            assert.equal(options.body.get('csrf_token'),'csrf-fixture');
            const result=url.endsWith('/preview')?{untaxed:200,tax:30,total:230,currency:'SAR',line_amounts:[200]}:
                {...boot,...data,id:42,version:'saved-version',editable:!data.submit,review:data.submit?'submitted':boot.review};
            return {json:async()=>({ok:true,result})};}});
    vm.runInContext(source,context);
    return {root,body,calls,tick:async()=>{if(timer){const fn=timer;timer=null;await fn();}},settle:async()=>{for(let i=0;i<8;i++)await Promise.resolve();}};
}
const f=mount(fixture);
assert(find(f.root,'Save Draft'));assert(find(f.root,'Submit for Approval'));
const qty=walk(f.root).find(n=>n['aria-label']==='quantity');qty.value='2';qty.handlers.input();
const price=walk(f.root).find(n=>n['aria-label']==='price_unit');price.value='100';price.handlers.input();
await f.tick();assert.equal(f.calls.at(-1).data.lines[0].quantity,2);assert.equal(f.calls.at(-1).data.lines[0].price_unit,100);
assert(find(f.root,'230.00 SAR'));assert(find(f.root,'30.00 SAR'));
assert.equal(f.root.querySelectorAll('[data-line-amount]')[0].textContent,'200.00');
find(f.root,'Save Draft').handlers.click();await f.settle();
assert.equal(f.calls.at(-1).data.submit,false);assert.equal(f.calls.at(-1).url,'/my/employee/accounting/api/save');
const m=mount({...fixture,id:42,editable:false,roles:{preparer:false,approver:false,monitor:true}});
assert(!find(m.root,'Save Draft'));assert(!find(m.root,'Submit for Approval'));assert(!find(m.root,'Approve & Post'));
assert(walk(m.root).filter(n=>n.tagName==='input').every(n=>n.disabled));
const a=mount({...fixture,id:42,editable:false,can_review:true,review:'submitted',roles:{preparer:false,approver:true,monitor:false}});
assert(find(a.root,'Approve & Post'));assert(find(a.root,'Return for Correction'));assert(!find(a.root,'Save Draft'));
find(a.root,'Return for Correction').handlers.click();
const comment=walk(a.body).find(n=>n['aria-label']==='Review comment');comment.value='Correct allocation';
find(a.body,'Return').handlers.click();await a.settle();
assert.equal(a.calls.at(-1).data.action,'return');assert.equal(a.calls.at(-1).data.version,'test-version');assert.equal(a.calls.at(-1).data.comment,'Correct allocation');
const p=mount({...fixture,kind:'planned',id:42});
assert(find(p.root,'Submit to CEO'));assert(!find(p.root,'Mark as Paid'));
console.log('PASS: actual frontend mount, numeric edits and server totals, CSRF/save payload, Monitor readonly controls, Approver actions/return and planned-payment execution boundary.');
// Rearranged detail fields still participate in draft edits and serialization.
const j=mount({...fixture,kind:'journals',lines:[{name:'Accrual',account_id:8,partner_id:7,debit:100,credit:0,amount_currency:100,date_maturity:'2026-11-01',tax_tag_ids:[11],grid_names:[{id:11,name:'Tax Grid'}],analytic_distribution:{'5':100}}]});
assert(find(j.root,'Foreign Amount'));assert(find(j.root,'Due Date'));assert(find(j.root,'Tax Grids'));assert(find(j.root,'Analytic Distribution'));
const foreign=walk(j.root).find(n=>n['aria-label']==='amount_currency');foreign.value='125';foreign.handlers.input();
const due=walk(j.root).find(n=>n['aria-label']==='date_maturity');due.value='2026-12-01';due.handlers.input();
find(j.root,'Save Draft').handlers.click();await j.settle();
const saved=j.calls.at(-1).data.lines[0];assert.equal(saved.amount_currency,125);assert.equal(saved.date_maturity,'2026-12-01');
assert.equal(saved.account_id,8);assert.deepEqual(saved.tax_tag_ids,[11]);assert.equal(saved.analytic_distribution['5'],100);
console.log('PASS: journal detail fields remain editable and preserve accounts, foreign amounts, due dates, tax grids and analytics in save payload.');
const normal=mount({...fixture,can_post:true,review_required:false,review:'not_required',roles:{preparer:true,direct:true,accountant:true,approver:false}});
assert(find(normal.root,'Post'));assert(!find(normal.root,'Submit for Approval'));assert(!find(normal.root,'Approve & Post'));
find(normal.root,'Post').handlers.click();
walk(normal.body).filter(n=>n.textContent==='Post').at(-1).handlers.click();await normal.settle();
assert.equal(normal.calls.at(-1).data.post,true);assert.equal(normal.calls.at(-1).data.submit,false);
const postedNormal=mount({...fixture,id:42,state:'posted',editable:false,can_post:false,review_required:false,roles:{preparer:true,direct:true,accountant:true,approver:false},history:[{author:'Employee',date:'2026-10-19',body:'Accounting: post by Employee.'}]});
assert(!find(postedNormal.root,'Reset to Draft'));assert(find(postedNormal.root,'Request Reset to Draft'));
assert(find(postedNormal.root,'Print Journal Entry')['href'].endsWith('&journal_entry=1'));
find(postedNormal.root,'Activity Log').handlers.click();assert(find(postedNormal.root,'Accounting: post by Employee.'));
console.log('PASS: direct Post dialog/save payload, no approval controls for ordinary accountant, reset request only, JV print link and activity log.');
