/** @odoo-module **/
// Native forms keep server validation and CSRF. Prevent repeated submissions;
// discard links intentionally leave unsaved edits behind.
let dirty=false,leaving=false;
document.addEventListener('input',event=>{if(event.target.closest('.aea-edit-form'))dirty=true;});
document.addEventListener('change',event=>{if(event.target.closest('.aea-edit-form'))dirty=true;});
document.addEventListener('click',event=>{if(event.target.closest('[data-aea-discard]'))leaving=true;});
document.addEventListener('submit',event=>{
    const form=event.target;if(!form.closest('.aea'))return;
    if(form.dataset.submitting==='true'){event.preventDefault();return;}
    if(dirty&&form.classList.contains('aea-operation')){event.preventDefault();window.alert('Save your form changes before using this action.');return;}
    if(form.dataset.confirm&&!window.confirm(form.dataset.confirm)){event.preventDefault();return;}
    form.dataset.submitting='true';leaving=true;
});
window.addEventListener('beforeunload',event=>{if(dirty&&!leaving){event.preventDefault();event.returnValue='';}});

window.addEventListener('pageshow',()=>{leaving=false;document.querySelectorAll('.aea form[data-submitting]').forEach(form=>delete form.dataset.submitting);});
