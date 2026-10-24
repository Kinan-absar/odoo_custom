/** @odoo-module **/
// Compact relation dropdowns and backend-style form notebooks.
function selectTab(notebook,index,focus=false){
    notebook.querySelectorAll('[data-aea-tab]').forEach((tab,i)=>{
        tab.setAttribute('aria-selected',String(i===index));
        tab.tabIndex=i===index?0:-1;
        if(i===index&&focus)tab.focus();
    });
    notebook.querySelectorAll('.aea-tab-panel').forEach((panel,i)=>panel.hidden=i!==index);
}
function initializeForms(){
    document.querySelectorAll('[data-aea-notebook]').forEach(notebook=>{
        notebook.querySelector('[role="tablist"]').hidden=false;
        selectTab(notebook,0);
    });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initializeForms);
else initializeForms();
document.addEventListener('click',event=>{
    const tab=event.target.closest('[data-aea-tab]');
    if(tab)selectTab(tab.closest('[data-aea-notebook]'),Number(tab.dataset.aeaTab));
    document.querySelectorAll('[data-aea-picker][open]').forEach(picker=>{
        if(!picker.contains(event.target))picker.open=false;
    });
});
document.addEventListener('keydown',event=>{
    const tab=event.target.closest('[data-aea-tab]');
    if(tab&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
        event.preventDefault();
        const notebook=tab.closest('[data-aea-notebook]');
        const count=notebook.querySelectorAll('[data-aea-tab]').length;
        const current=Number(tab.dataset.aeaTab);
        const index=event.key==='Home'?0:event.key==='End'?count-1:(current+(event.key==='ArrowRight'?1:-1)+count)%count;
        selectTab(notebook,index,true);
    }
    const picker=event.target.closest('[data-aea-picker]');
    if(picker&&event.key==='Escape'){picker.open=false;picker.querySelector('summary').focus();}
    if(picker&&event.key==='Enter'&&event.target.matches('input[type="search"]'))event.preventDefault();
});
document.addEventListener('input',event=>{
    if(!event.target.matches('.aea-picker-search'))return;
    const picker=event.target.closest('[data-aea-picker]');
    const query=event.target.value.trim().toLocaleLowerCase();
    picker.querySelectorAll('.aea-picker-option').forEach(option=>option.hidden=!option.textContent.toLocaleLowerCase().includes(query));
});
document.addEventListener('change',event=>{
    const picker=event.target.closest('[data-aea-picker]');
    if(!picker||!event.target.matches('input[type="checkbox"]'))return;
    const selected=Array.from(picker.querySelectorAll('input[type="checkbox"]:checked'),input=>input.closest('label').querySelector('span').textContent.trim());
    picker.querySelector('[data-aea-selection]').textContent=selected.join(', ')||'Select…';
});
// Show the appropriate notebook page before the browser focuses a required field.
let revealingInvalid=false;
document.addEventListener('invalid',event=>{
    if(revealingInvalid)return;
    revealingInvalid=true;queueMicrotask(()=>revealingInvalid=false);
    const panel=event.target.closest('.aea-tab-panel');
    if(!panel)return;
    const notebook=panel.closest('[data-aea-notebook]');
    const panels=Array.from(notebook.querySelectorAll('.aea-tab-panel'));
    selectTab(notebook,panels.indexOf(panel));
},true);
