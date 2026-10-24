import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
class Element{
    constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.value='';this.checked=false;this.hidden=false;this.dataset={};this.isConnected=true;this.text='';}
    append(...children){for(const child of children){child.parent=this;this.children.push(child);}}
    replaceChildren(...children){this.children=[];this.append(...children);}
    set textContent(value){this.text=value;this.children=[];}
    get textContent(){return this.text+this.children.map(child=>child.textContent).join('');}
    addEventListener(name,fn){(this.events[name]??=[]).push(fn);}
    emit(name,event={}){event.target??=this;event.preventDefault??=()=>{event.defaultPrevented=true;};for(const fn of this.events[name]||[])fn(event);return event;}
    closest(selector){if(selector==='label')return this.tag==='label'?this:this.parent?.closest(selector);if(selector==='[data-aea-generate-open]')return this.openButton?this:null;return null;}
    querySelectorAll(selector){const result=[];for(const child of this.children){if(selector==='label'&&child.tag==='label')result.push(child);if(selector==='input[name="employee_ids"]'&&child.name==='employee_ids')result.push(child);result.push(...child.querySelectorAll(selector));}return result;}
    showModal(){this.open=true;}
    close(){this.open=false;this.emit('close');}
    focus(){this.focused=true;}
}
const dialog=new Element('dialog'),form=new Element('form'),list=new Element(),message=new Element(),count=new Element(),all=new Element('input'),search=new Element('input'),submit=new Element('button'),structure=new Element('select'),cancel=new Element('button');
structure.value='';form.dataset.employeesUrl='/my/employee/admin/batches/70/employees';
const tag=new Element('input');tag.name='tag_ids';tag.value='80';
const fields={'[data-aea-generate-form]':form,'[data-aea-employees]':list,'[data-aea-generation-message]':message,'[data-aea-employees-count]':count,'[data-aea-employees-all]':all,'[data-aea-employee-search]':search,'[data-aea-generate-submit]':submit,'[data-aea-generate-close]':cancel,'[name="struct_id"]':structure,'[name="company_id"]':{value:'1'}};
dialog.querySelector=selector=>fields[selector];form.querySelector=selector=>fields[selector];form.querySelectorAll=selector=>selector==='[name="tag_ids"]:checked'&&tag.checked?[tag]:[];
const doc=new Element();doc.readyState='loading';doc.body=new Element('body');doc.querySelector=()=>dialog;
let pending=[];const context={document:doc,window:new Element(),URLSearchParams,fetch:url=>new Promise(resolve=>pending.push({url,resolve}))};doc.createElement=tag=>new Element(tag);
vm.runInNewContext(fs.readFileSync(new URL('../static/src/batch.js',import.meta.url),'utf8'),context);
doc.emit('DOMContentLoaded');
const opener=new Element('button');opener.openButton=true;
doc.emit('click',{target:opener,defaultPrevented:true});assert.equal(pending.length,0);
doc.emit('click',{target:opener});assert(dialog.open);assert(submit.disabled);
assert(pending[0].url.includes('company_id=1'));
pending.shift().resolve({ok:true,json:async()=>({employees:[{id:3,name:'First',contract:'Contract 3'},{id:5,name:'Second',contract:'Contract 5'}]})});
await new Promise(setImmediate);
assert.equal(list.children.length,2);assert.equal(submit.disabled,false);assert(count.textContent.startsWith('2 selected'));
search.value='Second';search.emit('input');assert(list.children[0].hidden);assert(!list.children[1].hidden);
all.checked=false;all.emit('change');assert(count.textContent.startsWith('1 selected'));
structure.value='90';structure.emit('change');assert.equal(list.children.length,0);assert(submit.disabled);assert(pending[0].url.includes('struct_id=90'));
tag.checked=true;form.emit('change',{target:tag});assert(pending[1].url.includes('tag_ids=80'));
pending[1].resolve({ok:true,json:async()=>({employees:[{id:8,name:'Newest',contract:'C8'}]})});await new Promise(setImmediate);
pending[0].resolve({ok:true,json:async()=>({employees:[{id:9,name:'Stale',contract:'C9'}]})});await new Promise(setImmediate);
assert(list.textContent.includes('Newest'));assert(!list.textContent.includes('Stale'));
list.children[0].children[0].checked=false;const event=form.emit('submit');assert(event.defaultPrevented);
cancel.emit('click');assert(!dialog.open);assert(opener.focused);assert.equal(list.children.length,0);
pending=[];doc.emit('click',{target:opener});pending.shift().resolve({ok:false,json:async()=>({error:'Batch is finalized'})});await new Promise(setImmediate);assert(submit.disabled);assert.equal(message.textContent,'Batch is finalized');
console.log('PASS: custom batch dialog, company/structure/tag lookup, multiple employee selection, visible select-all/search, stale responses, empty submit prevention, Cancel/focus, server errors.');
