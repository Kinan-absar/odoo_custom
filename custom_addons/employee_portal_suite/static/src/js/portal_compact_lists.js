/** @odoo-module **/
export function installEmployeePortalLists(doc=document,win=window){
    if(win.epsCompactListsInstalled)return;
    win.epsCompactListsInstalled=true;
    const interactive='a,button,input,select,textarea,label,summary,details,[contenteditable="true"]';
    function anchor(row){return row.dataset.epsRowLink?row.querySelector(row.dataset.epsRowLink):null;}
    function destination(row){const link=anchor(row);return row.dataset.epsRecordHref||link?.getAttribute('href');}
    function open(row,event){
        if(row.dataset.epsExpand){toggle(row);return;}
        const href=destination(row);if(!href)return;
        // Row activation only follows a displayed document link; never submits a form.
        row.classList.add('eps-row-selected');
        if(event.ctrlKey||event.metaKey||row.dataset.epsRecordTarget==='_blank'||anchor(row)?.getAttribute('target')==='_blank')win.open(href,'_blank','noopener');
        else win.location.assign(href);
    }
    function toggle(row){
        const panel=doc.getElementById(row.dataset.epsExpand);if(!panel)return;
        panel.hidden=!panel.hidden;row.setAttribute('aria-expanded',String(!panel.hidden));
        row.querySelector('[data-eps-detail-toggle]')?.setAttribute('aria-expanded',String(!panel.hidden));
    }
    function ready(){
        doc.querySelectorAll('.ep-portal-main .eps-compact-list td').forEach(cell=>{if(!cell.getAttribute('title'))cell.setAttribute('title',cell.textContent.trim().replace(/\s+/g,' '));});
        doc.querySelectorAll('.ep-portal-main [data-eps-row-link]').forEach(row=>{
            if(destination(row)){row.setAttribute('tabindex','0');row.setAttribute('role','link');row.classList.add('eps-record-row');}
        });
    }
    doc.addEventListener('click',event=>{
        const toggleButton=event.target.closest('[data-eps-detail-toggle]');
        const row=event.target.closest('[data-eps-record-href],[data-eps-row-link],[data-eps-expand]');
        if(!row||!row.closest('.ep-portal-main')||event.defaultPrevented||event.button>0)return;
        if(toggleButton){event.preventDefault();toggle(row);return;}
        if(event.target.closest(interactive))return;
        open(row,event);
    });
    doc.addEventListener('keydown',event=>{
        if(!['Enter',' '].includes(event.key)||event.defaultPrevented)return;
        const row=event.target.closest('[data-eps-record-href],[data-eps-row-link],[data-eps-expand]');
        if(!row||event.target!==row||!row.closest('.ep-portal-main'))return;
        if(!row.dataset.epsExpand&&!destination(row))return;
        event.preventDefault();open(row,event);
    });
    if(doc.readyState==='loading')doc.addEventListener('DOMContentLoaded',ready);else ready();
}
installEmployeePortalLists();
