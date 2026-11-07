/** @odoo-module **/
export function installEmployeePortalLists(doc=document,win=window){
    if(win.pbwCompactListsInstalled)return;
    win.pbwCompactListsInstalled=true;
    const interactive='a,button,input,select,textarea,label,summary,details,[contenteditable="true"]';
    function anchor(row){return row.dataset.pbwRowLink?row.querySelector(row.dataset.pbwRowLink):null;}
    function destination(row){const link=anchor(row);return row.dataset.pbwRecordHref||link?.getAttribute('href');}
    function open(row,event){
        if(row.dataset.pbwExpand){toggle(row);return;}
        const href=destination(row);if(!href)return;
        // Row activation only follows a displayed document link; never submits a form.
        row.classList.add('pbw-row-selected');
        if(event.ctrlKey||event.metaKey||row.dataset.pbwRecordTarget==='_blank'||anchor(row)?.getAttribute('target')==='_blank')win.open(href,'_blank','noopener');
        else win.location.assign(href);
    }
    function toggle(row){
        const panel=doc.getElementById(row.dataset.pbwExpand);if(!panel)return;
        panel.hidden=!panel.hidden;row.setAttribute('aria-expanded',String(!panel.hidden));
        row.querySelector('[data-pbw-detail-toggle]')?.setAttribute('aria-expanded',String(!panel.hidden));
    }
    function ready(){
        doc.querySelectorAll('.pbwep-portal-main .pbw-compact-list td').forEach(cell=>{if(!cell.getAttribute('title'))cell.setAttribute('title',cell.textContent.trim().replace(/\s+/g,' '));});
        doc.querySelectorAll('.pbwep-portal-main [data-pbw-row-link]').forEach(row=>{
            if(destination(row)){row.setAttribute('tabindex','0');row.setAttribute('role','link');row.classList.add('pbw-record-row');}
        });
    }
    doc.addEventListener('click',event=>{
        const toggleButton=event.target.closest('[data-pbw-detail-toggle]');
        const row=event.target.closest('[data-pbw-record-href],[data-pbw-row-link],[data-pbw-expand]');
        if(!row||!row.closest('.pbwep-portal-main')||event.defaultPrevented||event.button>0)return;
        if(toggleButton){event.preventDefault();toggle(row);return;}
        if(event.target.closest(interactive))return;
        open(row,event);
    });
    doc.addEventListener('keydown',event=>{
        if(!['Enter',' '].includes(event.key)||event.defaultPrevented)return;
        const row=event.target.closest('[data-pbw-record-href],[data-pbw-row-link],[data-pbw-expand]');
        if(!row||event.target!==row||!row.closest('.pbwep-portal-main'))return;
        if(!row.dataset.pbwExpand&&!destination(row))return;
        event.preventDefault();open(row,event);
    });
    if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',ready);else ready();
}
installEmployeePortalLists();
