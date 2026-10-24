import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../static/src/admin.js',import.meta.url),'utf8');
function fixture(){
 const events={},windows={},forms=[],alerts=[];
 const document={addEventListener:(name,fn)=>events[name]=fn,querySelectorAll:()=>forms};
 const window={addEventListener:(name,fn)=>windows[name]=fn,confirm:()=>false,alert:message=>alerts.push(message)};
 vm.runInNewContext(source,{document,window});
 function form(operation=false){return {dataset:{},classList:{contains:name=>operation&&name==='aea-operation'},closest:()=>true};}
 function submit(f){const event={target:f,preventDefault(){this.prevented=true;}};events.submit(event);return event;}
 return {events,windows,forms,alerts,form,submit,window};
}
let f=fixture(),form=f.form();assert(!f.submit(form).prevented);assert(f.submit(form).prevented);
f.forms.push(form);f.windows.pageshow();assert(!form.dataset.submitting);
f=fixture();form=f.form(true);form.dataset.confirm='Validate?';assert(f.submit(form).prevented);assert(!form.dataset.submitting);
f=fixture();f.events.input({target:{closest:()=>true}});let e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(e.prevented);
assert(f.submit(f.form(true)).prevented);assert(f.alerts[0].includes('Save'));
f.events.click({target:{closest:()=>true}});e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(!e.prevented);
f=fixture();form=f.form();f.events.input({target:{closest:()=>true}});assert(!f.submit(form).prevented);e={preventDefault(){this.prevented=true;}};f.windows.beforeunload(e);assert(!e.prevented);
console.log('PASS: actual form script blocks duplicate submits, preserves unsaved-edit protection, explicit Cancel discards, workflow actions require saved form, confirmation cancellation stays on page, and history restoration resets submission flags.');
