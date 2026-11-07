/** @odoo-module **/
// One delegated listener even when several workspace bundles are installed.
export function installRecordRows(doc=document,win=window){
    if(win.absarRecordRowsInstalled)return;
    win.absarRecordRowsInstalled=true;
    const interactive='a,button,input,select,textarea,label,summary,details,[contenteditable="true"]';
    function open(row,event){
        const href=row.dataset.recordHref;if(!href)return;
        row.classList.add('is-selected');
        if(event.ctrlKey||event.metaKey)win.open(href,'_blank','noopener');else win.location.assign(href);
    }
    doc.addEventListener('click',event=>{
        const row=event.target.closest('[data-record-href]');
        if(!row||event.defaultPrevented||event.button>0||event.target.closest(interactive))return;
        open(row,event);
    });
    doc.addEventListener('keydown',event=>{
        if(!['Enter',' '].includes(event.key)||event.defaultPrevented)return;
        const row=event.target.closest('[data-record-href]');if(!row||event.target!==row)return;
        event.preventDefault();open(row,event);
    });
}
installRecordRows();
