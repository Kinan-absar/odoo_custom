/** @odoo-module **/
// CSRF/version validation remains server-side. Confirmations use portal dialogs.
let dirty=false,leaving=false,activeDialog=null,dialogSequence=0;
function portalDialog(message,{title='Confirm Action',confirmLabel='Confirm',cancelLabel='Cancel'}={}){
    if(activeDialog)return Promise.resolve(false);
    return new Promise(resolve=>{
        const dialog=document.createElement('dialog');
        dialog.className='pbw-hr-dialog';activeDialog=dialog;
        const heading=document.createElement('h2');heading.id='pbw-hr-dialog-title-'+(++dialogSequence);heading.textContent=title;
        const body=document.createElement('p');body.textContent=message;
        dialog.setAttribute('aria-labelledby',heading.id);
        const actions=document.createElement('div');actions.className='pbw-hr-dialog-actions';
        let cancel;
        if(cancelLabel){
            cancel=document.createElement('button');cancel.type='button';cancel.className='pbw-hr-dialog-cancel';cancel.textContent=cancelLabel;
            cancel.addEventListener('click',()=>dialog.close('cancel'));actions.append(cancel);
        }
        const confirm=document.createElement('button');confirm.type='button';confirm.className='pbw-hr-dialog-confirm';confirm.textContent=confirmLabel;
        confirm.addEventListener('click',()=>dialog.close('confirm'));actions.append(confirm);
        dialog.append(heading,body,actions);
        const previousFocus=document.activeElement;
        dialog.addEventListener('close',()=>{
            const confirmed=dialog.returnValue==='confirm';dialog.remove();activeDialog=null;
            if(previousFocus?.isConnected)previousFocus.focus();
            resolve(confirmed);
        },{once:true});
        document.body.append(dialog);dialog.showModal();(cancel||confirm).focus();
    });
}
document.addEventListener('input',event=>{if(event.target.closest('.pbw-hr-edit-form')&&!event.target.classList?.contains('pbw-hr-picker-search'))dirty=true;});
document.addEventListener('change',event=>{if(event.target.closest('.pbw-hr-edit-form')&&!event.target.classList?.contains('pbw-hr-picker-search'))dirty=true;});
document.addEventListener('click',event=>{
    if(event.target.closest('[data-pbw-hr-discard]'))leaving=true;
    if(dirty&&event.target.closest('[data-pbw-hr-generate-open]')){
        event.preventDefault();
        portalDialog('Save your form changes before generating payslips.',{title:'Save Changes First',confirmLabel:'OK',cancelLabel:null});
    }
});
document.addEventListener('submit',async event=>{
    const form=event.target;if(event.defaultPrevented||!form.closest('.pbw-hr'))return;
    // A file download leaves the form on screen; allow another date range.
    if(form.dataset.pbwHrDownload==='true')return;
    if(form.dataset.submitting==='true'||form.dataset.awaitingConfirmation==='true'){event.preventDefault();return;}
    if(dirty&&form.classList.contains('pbw-hr-operation')){
        event.preventDefault();
        await portalDialog('Save your form changes before using this action.',{title:'Save Changes First',confirmLabel:'OK',cancelLabel:null});return;
    }
    if(form.dataset.confirm&&form.dataset.confirmed!=='true'){
        event.preventDefault();form.dataset.awaitingConfirmation='true';
        const submitter=event.submitter;
        let confirmed;
        try{confirmed=await portalDialog(form.dataset.confirm,{confirmLabel:submitter?.textContent?.trim()||'Confirm'});}
        finally{delete form.dataset.awaitingConfirmation;}
        if(confirmed&&form.isConnected!==false){
            form.dataset.confirmed='true';
            // requestSubmit retains browser validation, checkbox review and submitter values.
            try{form.requestSubmit(submitter||undefined);}finally{delete form.dataset.confirmed;}
        }
        return;
    }
    delete form.dataset.confirmed;form.dataset.submitting='true';leaving=true;
});
// Closing/reloading the browser still uses its required unsaved-changes protection.
window.addEventListener('beforeunload',event=>{if(dirty&&!leaving){event.preventDefault();event.returnValue='';}});
window.addEventListener('pageshow',()=>{
    leaving=false;if(activeDialog)activeDialog.close('cancel');
    document.querySelectorAll('.pbw-hr form').forEach(form=>{
        delete form.dataset.submitting;delete form.dataset.awaitingConfirmation;delete form.dataset.confirmed;
    });
});
