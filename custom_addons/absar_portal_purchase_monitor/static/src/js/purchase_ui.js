/** @odoo-module **/
/** Small portal-only form controls. No backend services or model RPC. */
export function createPurchaseUI({root, post, companyId}) {
    const text = (tag, value, className='') => {
        const node = document.createElement(tag); node.textContent = value ?? ''; node.className = className; return node;
    };
    const button = (label, callback, cls='btn btn-light') => {
        const node = text('button',label,cls); node.type='button';node.addEventListener('click',callback);return node;
    };
    const input = (value,type,onChange) => {
        const node=document.createElement('input');node.className='form-control';node.type=type||'text';node.value=value??'';
        if(type==='number')node.step='any';node.addEventListener('change',()=>onChange(node.value));return node;
    };
    const field = (label,node,host,hint='') => {
        const wrap=document.createElement('label');wrap.append(text('span',label),node);
        if(hint)wrap.append(text('small',hint,'apw-help'));host.append(wrap);return node;
    };
    const modal = title => {
        const dialog=document.createElement('dialog');dialog.className='apw-dialog';
        const head=text('div','','apw-heading');head.append(text('h3',title),button('Close',()=>dialog.close()));
        const body=document.createElement('div'),foot=text('div','','apw-actions');dialog.append(head,body,foot);
        const focus=document.activeElement;dialog.addEventListener('close',()=>{dialog.remove();focus?.focus();});root.append(dialog);dialog.showModal();return {dialog,body,foot};
    };
    const searchMore=(kind,query,onSelect,extras={})=>{
        const view=modal('Search '+kind),search=input(query,'search',()=>{}),list=text('div','','apw-search-results'),pager=text('div','','apw-pager');let offset=0,sequence=0;
        async function load(){const current=++sequence;list.replaceChildren(text('p','Searching…'));try{
            const result=await post('/lookup',{kind,q:search.value,company_id:companyId,offset,...extras});if(current!==sequence)return;
            list.replaceChildren();for(const item of result.items)list.append(button(item.label,()=>{view.dialog.close();onSelect(item);},'apw-option'));
            if(!result.items.length)list.append(text('p','No matching records'));
            pager.replaceChildren();if(offset)pager.append(button('Previous',()=>{offset=Math.max(0,offset-30);load();}));pager.append(text('span','Page '+(offset/30+1)));if(result.more)pager.append(button('Next',()=>{offset+=30;load();}));
        }catch(error){list.replaceChildren(text('p',error.message));}}
        search.setAttribute('aria-label','Search records');search.addEventListener('input',()=>{offset=0;load();});view.body.append(search,list);view.foot.append(pager);load();search.focus();
    };
    const lookup=(kind,selected,onSelect)=>{
        const wrap=text('div','','apw-lookup'),box=input(selected?.label||'','search',()=>{}),options=text('div','','apw-options');
        box.setAttribute('aria-label',kind+' search');box.setAttribute('role','combobox');box.setAttribute('aria-expanded','false');box.autocomplete='off';
        options.hidden=true;options.setAttribute('popover','manual');options.setAttribute('role','listbox');
        const close=()=>{if(typeof options.hidePopover==='function' && options.matches(':popover-open'))options.hidePopover();options.hidden=true;box.setAttribute('aria-expanded','false');};
        const show=()=>{const rect=box.getBoundingClientRect();options.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-300))+'px';options.style.top=Math.min(rect.bottom+2,window.innerHeight-240)+'px';options.style.width=Math.min(Math.max(rect.width,280),window.innerWidth-24)+'px';options.hidden=false;if(typeof options.showPopover==='function')options.showPopover();box.setAttribute('aria-expanded','true');};
        let timer,seq=0;
        async function search(){
            const current=++seq;options.replaceChildren(text('div','Searching…','apw-help'));show();
            try{
                const result=await post('/lookup',{kind,q:box.value,company_id:companyId});if(current!==seq)return;
                options.replaceChildren();
                for(const item of result.items){const choice=button(item.label,()=>{box.value=item.label;close();onSelect(item);},'apw-option');choice.setAttribute('role','option');options.append(choice);}
                if(!result.items.length)options.append(text('div','No matches','apw-help'));
                options.append(button('Search More…',()=>{close();searchMore(kind,box.value,item=>{box.value=item.label;onSelect(item);});},'apw-option'));
                options.append(button('Clear selection',()=>{box.value='';close();onSelect(null);},'apw-option'));
            }catch(error){options.replaceChildren(text('div',error.message,'apw-help'));}
        }
        box.addEventListener('focus',search);box.addEventListener('input',()=>{onSelect(null);clearTimeout(timer);timer=setTimeout(search,220);});
        box.addEventListener('keydown',event=>{if(event.key==='Escape')close();if(event.key==='ArrowDown'){event.preventDefault();options.querySelector('button')?.focus();}});
        wrap.addEventListener('focusout',()=>setTimeout(()=>{if(!wrap.contains(document.activeElement))close();},100));
        wrap.append(box,options);return wrap;
    };
    return {text,button,input,field,modal,lookup,searchMore};
}
