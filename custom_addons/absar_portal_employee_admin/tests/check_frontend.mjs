import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../static/src/admin.js',import.meta.url),'utf8');
function fixture(){
 const events={},windows={},forms=[],nodes=[],dialogs=[];
 class Element{
  constructor(tag){this.tag=tag;this.events={};this.children=[];this.isConnected=true;nodes.push(this);}
  setAttribute(k,v){this[k]=v;}
  append(...children){this.children.push(...children);}
  addEventListener(k,f){this.events[k]=f;}
  showModal(){this.open=true;dialogs.push(this);}
  focus(){this.focused=true;}
  close(value){this.returnValue=value;this.open=false;this.events.close();}
  remove(){this.isConnected=false;}
 }
 const document={activeElement:null,body:new Element('body'),createElement:tag=>new Element(tag),addEventListener:(name,fn)=>events[name]=fn,querySelectorAll:()=>forms};
 const window={addEventListener:(name,fn)=>windows[name]=fn,confirm:()=>{throw Error('Native confirm must not be used');},alert:()=>{throw Error('Native alert must not be used');}};
 vm.runInNewContext(source,{document,window});
 function form(operation=false){const f={dataset:{},isConnected:true,classList:{contains:name=>operation&&name==='aea-operation'},closest:()=>true,requests:0};f.requestSubmit=submitter=>{f.requests++;submit(f,submitter);};forms.push(f);return f;}
 function submit(f,submitter){const event={target:f,submitter,preventDefault(){this.prevented=true;}};const promise=events.submit(event);return {event,promise};}
 const clickButton=label=>nodes.findLast(n=>n.tag==='button'&&n.textContent===label).events.click();
 return {events,windows,forms,dialogs,nodes,form,submit,clickButton};
}
let f=fixture(),form=f.form();assert(!f.submit(form).event.prevented);assert(f.submit(form).event.prevented);
f.windows.pageshow();assert(!form.dataset.submitting);
f=fixture();form=f.form(true);form.dataset.confirm='Change the contract status?';
let run=f.submit(form,{textContent:'Start Contract'});assert(run.event.prevented);assert.equal(f.dialogs.length,1);assert.equal(form.requests,0);
assert(f.submit(form).event.prevented);assert.equal(f.dialogs.length,1);
f.clickButton('Cancel');await run.promise;assert.equal(form.requests,0);assert(!form.dataset.submitting);assert(!form.dataset.awaitingConfirmation);
run=f.submit(form,{textContent:'Start Contract'});f.clickButton('Start Contract');await run.promise;
assert.equal(form.requests,1);assert.equal(form.dataset.submitting,'true');assert(!form.dataset.confirmed);
assert(f.submit(form).event.prevented);
f=fixture();form=f.form(true);f.events.input({target:{closest:()=>true}});
run=f.submit(form);assert(run.event.prevented);assert.equal(f.dialogs.length,1);assert(f.nodes.some(n=>n.tag==='h2'&&n.textContent==='Save Changes First'));
f.clickButton('OK');await run.promise;assert.equal(form.requests,0);
let e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(e.prevented);
f.events.click({target:{closest:()=>true}});e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(!e.prevented);
f=fixture();form=f.form();f.events.input({target:{closest:()=>true}});assert(!f.submit(form).event.prevented);e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(!e.prevented);
f=fixture();form=f.form(true);form.dataset.confirm='Validate?';run=f.submit(form);f.windows.pageshow();await run.promise;assert.equal(form.requests,0);assert(!form.dataset.awaitingConfirmation);
console.log('PASS: portal confirmation Cancel/Confirm, repeated clicks, original submitter and validated resubmit, save-first popup, history restoration, unsaved protection; native alert/confirm never called.');
