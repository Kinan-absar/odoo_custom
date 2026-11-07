/** @odoo-module **/
// Employee selection for one fixed, company-scoped payroll batch.
function initializeBatchGeneration(){
    const dialog=document.querySelector('[data-aea-generate-dialog]');
    if(!dialog)return;
    document.body.append(dialog);
    const form=dialog.querySelector('[data-aea-generate-form]');
    const list=form.querySelector('[data-aea-employees]');
    const message=form.querySelector('[data-aea-generation-message]');
    const counter=form.querySelector('[data-aea-employees-count]');
    const all=form.querySelector('[data-aea-employees-all]');
    const search=form.querySelector('[data-aea-employee-search]');
    const submit=form.querySelector('[data-aea-generate-submit]');
    let sequence=0,loading=false,opener=null;
    const boxes=()=>Array.from(list.querySelectorAll('input[name="employee_ids"]'));
    function update(){
        const rows=boxes(),selected=rows.filter(box=>box.checked);
        const visible=rows.filter(box=>!box.closest('label').hidden);
        counter.textContent=selected.length+' selected / '+rows.length+' eligible';
        all.checked=visible.length>0&&visible.every(box=>box.checked);
        all.indeterminate=visible.some(box=>box.checked)&&!all.checked;
        all.disabled=loading||!visible.length;
        submit.disabled=loading||!selected.length;
    }
    async function refresh(){
        const current=++sequence;loading=true;list.replaceChildren();
        message.textContent='Loading eligible employees…';update();
        const params=new URLSearchParams({company_id:form.querySelector('[name="company_id"]').value,struct_id:form.querySelector('[name="struct_id"]').value});
        form.querySelectorAll('[name="tag_ids"]:checked').forEach(box=>params.append('tag_ids',box.value));
        try{
            const response=await fetch(form.dataset.employeesUrl+'?'+params,{credentials:'same-origin'});
            const data=await response.json();
            if(!response.ok||data.error)throw new Error(data.error||'Unable to load employees. Reopen this window to retry.');
            if(current!==sequence)return;
            for(const employee of data.employees){
                const row=document.createElement('label');row.className='aea-batch-employee';
                const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.name='employee_ids';checkbox.value=String(employee.id);checkbox.checked=true;
                const text=document.createElement('span');const name=document.createElement('strong');name.textContent=employee.name;
                const contract=document.createElement('small');contract.textContent=employee.contract;
                text.append(name,contract);row.append(checkbox,text);list.append(row);
            }
            message.textContent=data.employees.length?'':'No eligible employees match these filters. Check contracts and existing payslips.';
        }catch(error){if(current===sequence)message.textContent=error.message;}
        finally{if(current===sequence){loading=false;filter();}}
    }
    function filter(){
        const query=search.value.trim().toLocaleLowerCase();
        list.querySelectorAll('label').forEach(row=>row.hidden=!row.textContent.toLocaleLowerCase().includes(query));update();
    }
    document.addEventListener('click',event=>{
        const button=event.target.closest('[data-aea-generate-open]');
        if(!button||event.defaultPrevented)return;
        opener=button;dialog.showModal();search.value='';refresh();
    });
    window.addEventListener('pageshow',()=>{if(dialog.open)dialog.close();});
    form.querySelector('[data-aea-generate-close]').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{sequence++;loading=false;list.replaceChildren();if(opener?.isConnected)opener.focus();});
    form.querySelector('[name="struct_id"]').addEventListener('change',refresh);
    form.addEventListener('change',event=>{
        if(event.target.name==='tag_ids')refresh();
        else if(event.target.name==='employee_ids')update();
    });
    search.addEventListener('input',filter);
    search.addEventListener('keydown',event=>{if(event.key==='Enter')event.preventDefault();});
    all.addEventListener('change',()=>{boxes().forEach(box=>{if(!box.closest('label').hidden)box.checked=all.checked;});update();});
    form.addEventListener('submit',event=>{
        if(loading||!boxes().some(box=>box.checked)){event.preventDefault();message.textContent='Select at least one employee.';}
        else if(boxes().filter(box=>box.checked).length>500){event.preventDefault();message.textContent='Select no more than 500 employees at a time.';}
    });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initializeBatchGeneration);
else initializeBatchGeneration();
