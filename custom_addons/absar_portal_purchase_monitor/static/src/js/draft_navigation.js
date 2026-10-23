/** @odoo-module **/
/* Save editable documents as drafts before leaving; never submit or post. */
export function installDraftNavigation({isDirty, save, onError}) {
    let leaving=false, pending=null;
    const dirty=()=>!leaving&&isDirty();
    async function leave(next,restoreURL=null){
        if(pending)return pending;
        const job=(async()=>{
            try{
                document.activeElement?.blur?.();
                if(dirty() && await save()!==true)throw new Error('Draft was not saved. Complete the required fields before leaving.');
                leaving=true;next();return true;
            }catch(error){
                if(restoreURL)window.history.replaceState(null,'',restoreURL);
                onError(error);return false;
            }
        })();
        pending=job;job.then(()=>{if(pending===job)pending=null;},()=>{if(pending===job)pending=null;});return job;
    }
    document.addEventListener?.('click',event=>{
        if(event.defaultPrevented||event.button>0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
        const link=event.target.closest?.('a[href]');
        if(!link||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
        const url=new URL(link.href,window.location.href),current=new URL(window.location.href);
        if(!['http:','https:'].includes(url.protocol)||(url.origin===current.origin&&url.pathname===current.pathname&&url.search===current.search))return;
        if(link.hasAttribute('data-draft-cancel')){
            event.preventDefault();event.stopImmediatePropagation();
            leaving=true;window.location.assign(url.href);return;
        }
        document.activeElement?.blur?.();
        if(!dirty())return;
        event.preventDefault();event.stopImmediatePropagation();
        leave(()=>window.location.assign(url.href));
    },true);
    window.navigation?.addEventListener('navigate',event=>{
        if(event.defaultPrevented||event.hashChange||event.downloadRequest!=null||event.formData)return;
        document.activeElement?.blur?.();
        if(!dirty())return;
        const target=event.destination.url,source=window.location.href;
        const currentIndex=window.navigation.currentEntry?.index;
        const delta=event.destination.index>=0&&currentIndex>=0?event.destination.index-currentIndex:0;
        const next=()=>event.navigationType==='traverse'&&delta?window.history.go(delta):
            event.navigationType==='reload'?window.location.reload():
            event.navigationType==='replace'?window.location.replace(target):window.location.assign(target);
        if(event.cancelable){event.preventDefault();leave(next);}
        else if(event.canIntercept){
            event.intercept({focusReset:'manual',scroll:'manual',handler:()=>leave(()=>window.location.replace(target),source)});
        }
    });
    // Closing the tab or navigating beyond browser interception support cannot
    // await an HTTP response. Keep the native protection against losing edits.
    window.addEventListener('beforeunload',event=>{if(dirty()){event.preventDefault();event.returnValue='';}});
    return {leave};
}
