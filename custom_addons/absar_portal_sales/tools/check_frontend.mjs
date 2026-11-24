import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../static/src/js/portal_sales.js',import.meta.url),'utf8');
const start=source.indexOf("  form?.addEventListener('submit', async event => {");
const end=source.indexOf('\n  });',start);
const handler=source.slice(start,end).replace("  form?.addEventListener('submit', async event => {",'this.saveLine = async event => {')+'\n};';
class Element {
 constructor(){this.children=[];this.dataset={};this.disabled=false;}
 appendChild(child){this.children.push(child);}
 querySelector(){return null;}
 querySelectorAll(){return [];}
 setAttribute(){}
 focus(){}
}
const review=new Element();review.disabled=true;
const save=new Element(),editRow=new Element(),openButton=new Element();
editRow.querySelector=s=>s==='.aps-boq-save'?save:null;
const form=new Element();form.action='/line/add';form.reportValidity=()=>true;form.reset=()=>{};
const rows=[];const linkRow={parentNode:{insertBefore:row=>rows.push(row)}};
const total=new Element();let success=true;
const context=vm.createContext({form,editRow,openButton,sync(){},FormData:class {},
 document:{createElement:()=>new Element(),querySelector:s=>s==='.aps-boq-add-link-row'?linkRow:s==='[data-aps-submit-review]'?review:s==='.aps-boq-total-value'?total:null},
 fetch:async()=>({ok:success,json:async()=>({ok:success,error:'Rejected',description:'QA item',unit:'AU',qty:1,rate:1,subtotal:1,total:1,currency:'SAR',delete_url:'/line/delete'})})});
vm.runInContext(handler,context);
await context.saveLine({preventDefault(){}});
assert.equal(rows.length,1);assert.equal(review.disabled,false);
assert.equal(total.textContent,'1.00 SAR');assert.equal(save.disabled,false);
review.disabled=true;success=false;
await context.saveLine({preventDefault(){}});
assert.equal(rows.length,1);assert.equal(review.disabled,true);
console.log('PASS: first successful inline line save enables Submit without reload; a rejected save never enables it.');
