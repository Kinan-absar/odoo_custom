/** @odoo-module **/
// Compact relation dropdowns and backend-style form notebooks.
function selectTab(notebook,index,focus=false){
    const tabs=Array.from(notebook.querySelectorAll('[data-aea-tab]'));
    const selected=tabs[index];
    if(!selected)return;
    const target=selected.getAttribute('aria-controls');
    tabs.forEach(tab=>{
        const active=tab===selected;
        tab.setAttribute('aria-selected',String(active));
        tab.tabIndex=active?0:-1;
        if(active&&focus)tab.focus();
    });
    notebook.querySelectorAll('.aea-tab-panel').forEach(panel=>panel.hidden=panel.id!==target);
}
function tabIndex(notebook,tab){return Array.from(notebook.querySelectorAll('[data-aea-tab]')).indexOf(tab);}
function initializeForms(){
    document.querySelectorAll('[data-aea-edit]').forEach(initializeContractSelector);
    document.querySelectorAll('[data-aea-notebook]').forEach(notebook=>{
        notebook.querySelector('[role="tablist"]').hidden=false;
        selectTab(notebook,0);
    });
}
function initializeContractSelector(form){
    const employee=form.querySelector('[name="employee_id"]');
    const contract=form.querySelector('[name="contract_id"]');
    const company=form.querySelector('[name="company_id"]');
    if(!employee||!contract||!company||!['payslips','work-entries'].includes(form.dataset?.aeaKind))return;
    let sequence=0;
    async function reload(clear=false){
        const current=++sequence;
        const selected=clear?'':contract.value;
        contract.replaceChildren(new Option(employee.value?'Loading…':'Select employee first…',''));
        contract.setCustomValidity('');
        if(!employee.value)return;
        contract.setCustomValidity('Wait for contracts to load.');
        try{
            const params=new URLSearchParams({company_id:company.value,kind:form.dataset.aeaKind,employee_id:employee.value});
            const response=await fetch('/my/employee/admin/contract-options?'+params,{credentials:'same-origin'});
            if(!response.ok)throw new Error('Contract lookup failed');
            const data=await response.json();
            if(current!==sequence)return;
            contract.replaceChildren(new Option(data.options.length?'Select…':'No contracts for this employee',''));
            data.options.forEach(([id,label])=>contract.add(new Option(label,String(id))));
            contract.value=data.options.some(([id])=>String(id)===selected)?selected:'';
            contract.setCustomValidity('');
        }catch(error){
            if(current!==sequence)return;
            contract.replaceChildren(new Option('Unable to load contracts. Select employee again.',''));
            contract.setCustomValidity('Unable to load contracts. Select employee again.');
        }
    }
    employee.addEventListener('change',()=>reload(true));
    // Also refresh restored browser values and values retained after a validation error.
    reload();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initializeForms);
else initializeForms();
document.addEventListener('click',event=>{
    const tab=event.target.closest('[data-aea-tab]');
    if(tab){const notebook=tab.closest('[data-aea-notebook]');selectTab(notebook,tabIndex(notebook,tab));}
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
        const current=tabIndex(notebook,tab);
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
    const tabs=Array.from(notebook.querySelectorAll('[data-aea-tab]'));
    selectTab(notebook,tabs.findIndex(tab=>tab.getAttribute('aria-controls')===panel.id));
},true);
