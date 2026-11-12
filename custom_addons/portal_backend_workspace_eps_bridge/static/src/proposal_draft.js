/** @odoo-module **/
// Independent draft editor, backed by the installed proposal engine through the
// existing bridge. No quotation or proposal child is created until Save Draft.
export function mountProposalDraft(root) {
    const header = document.getElementById('pbw-sales-new-details');
    const kind = header?.querySelector('[name="kind"]');
    const payload = header?.querySelector('[name="proposal_payload"]');
    if (!header || !kind || !payload) return null;
    const boot = JSON.parse(root.dataset.boot || '{}');
    const sectionHost = root.querySelector('[data-pbw-proposal-sections]');
    const paymentHost = root.querySelector('[data-pbw-proposal-payments]');
    const status = header.querySelector('[data-pbw-proposal-error]');
    const template = header.querySelector('[name="template_id"]');
    const title = header.querySelector('[name="title"]');
    const customer = header.querySelector('[name="partner_id"]');
    const loadButton = header.querySelector('[data-pbw-proposal-load]');
    let state = {sections: [], payments: []};
    let untaxed = 0, currency = '', loading = false, loadSerial = 0;
    const clone = value => JSON.parse(JSON.stringify(value));
    function el(tag, text='', cls='') {
        const node = document.createElement(tag); node.className = cls;
        if (text) node.textContent = text;
        return node;
    }
    function error(message='') { status.textContent = message; status.hidden = !message; }
    function sync(notify=true) {
        payload.value = JSON.stringify(state);
        if (notify) payload.dispatchEvent(new Event('change', {bubbles: true}));
        totals();
    }
    function safeHTML(value) {
        const fragment = document.createElement('template');
        fragment.innerHTML = String(value || '');
        fragment.content.querySelectorAll('script,style,iframe,object,embed,link,meta,base,form,input,button,textarea,select,svg,math').forEach(n => n.remove());
        fragment.content.querySelectorAll('*').forEach(node => {
            Array.from(node.attributes).forEach(attr => {
                const value = attr.value.replace(/[\s\u0000-\u001f]/g, '');
                if (/^on/i.test(attr.name) || attr.name === 'srcdoc' || attr.name === 'formaction'
                    || (['href', 'src', 'xlink:href'].includes(attr.name) && !/^(https?:|mailto:|tel:|\/|#)/i.test(value))) node.removeAttribute(attr.name);
            });
        });
        return fragment.innerHTML;
    }
    function input(value, label, onChange, type='text') {
        const node = el('input', '', 'form-control'); node.type = type;
        node.value = value ?? ''; node.setAttribute('aria-label', label);
        node.addEventListener('input', () => { onChange(node.value); error(); sync(); });
        return node;
    }
    function button(label, fn, cls='btn btn-sm btn-outline-secondary') {
        const node = el('button', label, cls); node.type = 'button';
        node.addEventListener('click', fn); return node;
    }
    function move(array, index, step) {
        const target = index + step;
        if (target < 0 || target >= array.length) return;
        const [row] = array.splice(index, 1); array.splice(target, 0, row);
        render(); sync();
    }
    function richEditor(row) {
        const wrap = el('div', '', 'pbw-sales-editor');
        const toolbar = el('div', '', 'pbw-sales-editor-toolbar');
        const body = el('div', '', 'pbw-sales-editor-body');
        body.contentEditable = 'true'; body.setAttribute('role', 'textbox');
        body.setAttribute('aria-label', 'Section content'); body.setAttribute('aria-multiline', 'true');
        body.innerHTML = safeHTML(row.content);
        const record = () => { row.content = safeHTML(body.innerHTML); sync(); };
        for (const [label, command] of [['B','bold'], ['I','italic'], ['U','underline'], ['Bullet list','insertUnorderedList'], ['Numbered list','insertOrderedList']]) {
            const control = button(label, () => { body.focus(); document.execCommand(command, false, null); record(); });
            control.addEventListener('mousedown', event => event.preventDefault());
            toolbar.append(control);
        }
        const size = el('select', '', 'pbw-sales-font-size'); size.setAttribute('aria-label', 'Text size');
        for (const [value, label] of [['','Text size'],['2','Small'],['3','Normal'],['4','Large'],['5','Extra large']]) { const op = el('option', label); op.value = value; size.append(op); }
        size.addEventListener('change', () => { if (size.value) { body.focus(); document.execCommand('fontSize', false, size.value); record(); size.value=''; } });
        toolbar.append(size); body.addEventListener('input', record);
        body.addEventListener('paste', event => {
            event.preventDefault();
            const html = event.clipboardData?.getData('text/html');
            if (html) document.execCommand('insertHTML', false, safeHTML(html));
            else document.execCommand('insertText', false, event.clipboardData?.getData('text/plain') || '');
            record();
        });
        wrap.append(toolbar, body); return wrap;
    }
    function renderSections() {
        sectionHost.replaceChildren();
        if (!state.sections.length) sectionHost.append(el('p', 'Load a template or add a technical section.', 'text-muted'));
        state.sections.forEach((row, index) => {
            const details = el('details', '', 'pbw-sales-section pbw-sales-section-compact'); details.open = true;
            const summary = el('summary', '', 'pbw-sales-section-heading');
            const number = el('span', String(index+1), 'pbw-sales-section-number');
            const caption = el('span', row.name || 'New section', 'pbw-sales-section-name');
            summary.append(number, caption); details.append(summary);
            const inner = el('div', '', 'pbw-sales-section-expanded');
            const actions = el('div', '', 'd-flex gap-2 mb-2');
            const up = button('Move up', () => move(state.sections, index, -1)); up.disabled=index===0;
            const down = button('Move down', () => move(state.sections, index, 1)); down.disabled=index===state.sections.length-1;
            actions.append(up, down, button('Delete Section', () => {state.sections.splice(index,1);render();sync();},'btn btn-sm btn-outline-danger'));
            inner.append(actions, el('label','Section type'));
            const select = el('select', '', 'form-select'); select.setAttribute('aria-label','Section type');
            for (const [value,label] of boot.types || []) { const op=el('option',label);op.value=value;select.append(op); }
            select.value=row.section_type;
            select.addEventListener('change',()=>{
                const previous=boot.defaults?.[row.section_type];const next=boot.defaults?.[select.value];
                row.section_type=select.value;
                if (!row.name || row.name===previous?.name) row.name=next?.name||'';
                if (!row.content && next?.content) row.content=next.content;
                renderSections();sync();
            });
            inner.append(select, el('label','Section title','mt-2'));
            const name=input(row.name,'Section title',v=>{row.name=v;caption.textContent=v||'New section';});name.required=true;name.maxLength=180;
            inner.append(name, el('label','Content','mt-2'),richEditor(row));
            const flags=el('div','','d-flex gap-3 mt-2');
            for(const [key,label] of [['include_in_report','Include in PDF'],['page_break_before','New PDF page']]){
                const labelNode=el('label');const checkbox=el('input');checkbox.type='checkbox';checkbox.checked=Boolean(row[key]);
                checkbox.addEventListener('change',()=>{row[key]=checkbox.checked;sync();});labelNode.append(checkbox,document.createTextNode(' '+label));flags.append(labelNode);
            }
            inner.append(flags);details.append(inner);sectionHost.append(details);
        });
    }
    function renderPayments() {
        paymentHost.replaceChildren();
        state.payments.forEach((row,index)=>{
            const tr=el('tr');tr.append(el('td',String(index+1)));
            const fields=[['name','Milestone','text'],['percentage','Percentage','number'],['due_condition','Due condition','text']];
            for(const [key,label,type] of fields){const td=el('td');const field=input(row[key],label,v=>{row[key]=v;},type);
                if(key==='percentage'){field.min='0';field.max='100';field.step='0.01';field.required=true;}
                if(key==='name'){field.required=true;field.maxLength=180;}
                if(key==='due_condition')field.maxLength=255;
                td.append(field);tr.append(td);
            }
            const amount=el('td','','pbw-proposal-payment-amount');amount.dataset.index=String(index);tr.append(amount);
            const td=el('td');const controls=el('div','','d-flex gap-2');
            const up=button('Up',()=>move(state.payments,index,-1));up.disabled=index===0;
            const down=button('Down',()=>move(state.payments,index,1));down.disabled=index===state.payments.length-1;
            controls.append(up,down,button('Remove',()=>{state.payments.splice(index,1);renderPayments();sync();},'btn btn-sm btn-outline-danger'));td.append(controls);tr.append(td);paymentHost.append(tr);
        });
        totals();
    }
    function totals() {
        root.querySelectorAll('.pbw-proposal-payment-amount').forEach(node=>{
            const rate=Number(state.payments[Number(node.dataset.index)]?.percentage||0);
            const amount=Number.isFinite(rate)?untaxed*rate/100:0;
            node.textContent=amount.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})+(currency?' '+currency:'');
        });
        const rate=state.payments.reduce((sum,row)=>sum+(Number(row.percentage)||0),0);
        const node=root.querySelector('[data-pbw-proposal-payment-total]');
        node.textContent='Total: '+rate.toFixed(2)+'%. Amounts exclude VAT. '+(state.payments.length&&Math.abs(rate-100)>0.005?'Milestones must total 100% before printing.':'');
    }
    function render(){renderSections();renderPayments();}
    function companyId(){const specific=customer?.selectedOptions[0]?.dataset.companyId;return specific&&specific!=='0'?specific:header.dataset.defaultCompanyId;}
    function filterTemplates(){
        for(const op of template?.options||[]){const c=op.dataset.companyId;const unavailable=Boolean(op.value&&c&&c!=='0'&&c!==companyId());op.disabled=unavailable;op.hidden=unavailable;}
        if(template?.selectedOptions[0]?.disabled){template.value='';error('Select a template for the current customer company. Existing draft text is preserved.');}
    }
    function toggle(){
        const on=kind.value==='technical';root.hidden=!on;
        header.querySelectorAll('.pbw-proposal-new-header').forEach(node=>{node.hidden=!on;node.querySelectorAll('input,textarea,select,button').forEach(field=>{field.disabled=!on;});});
        if(on)filterTemplates();sync(false);
    }
    kind.addEventListener('change',toggle);
    customer?.addEventListener('change',()=>{loadSerial++;filterTemplates();});
    root.querySelector('[data-pbw-proposal-add-section]').addEventListener('click',()=>{
        if(state.sections.length>=100){error('Use at most 100 technical sections.');return;}
        const base=boot.defaults?.custom||{section_type:'custom',name:'Custom Section',content:'',include_in_report:true,page_break_before:false};
        state.sections.push(clone(base));renderSections();sync();
    });
    root.querySelector('[data-pbw-proposal-add-payment]').addEventListener('click',()=>{
        if(state.payments.length>=50){error('Use at most 50 payment milestones.');return;}
        state.payments.push({name:'',percentage:0,due_condition:''});renderPayments();sync();
    });
    let replacementConsent=false;
    const confirmation=el('div','','alert alert-warning mt-2');confirmation.hidden=true;
    confirmation.append(el('p','Replace the draft proposal sections and milestones? Quotation lines will not change.'));
    confirmation.append(button('Replace proposal content',()=>{replacementConsent=true;confirmation.hidden=true;loadButton.click();},'btn btn-sm btn-outline-primary'),button('Keep draft',()=>{confirmation.hidden=true;}));
    loadButton.after(confirmation);
    loadButton.addEventListener('click',async()=>{
        if(loading)return;if(!template.value){error('Choose a proposal template first.');return;}
        if((state.sections.length||state.payments.length)&&!replacementConsent){confirmation.hidden=false;return;}
        replacementConsent=false;
        const serial=++loadSerial;loading=true;loadButton.disabled=true;error();
        try{
            const response=await fetch('/my/workspace/sales/proposal-template-preview',{method:'POST',credentials:'same-origin',body:new URLSearchParams({csrf_token:root.dataset.csrf,template_id:template.value,partner_id:customer?.value||''})});
            if(!response.ok||!(response.headers.get('content-type')||'').includes('application/json'))throw new Error('This template could not be loaded. Check its company and your Sales access.');
            const data=await response.json();
            if(serial!==loadSerial)throw new Error('The customer changed while loading. Load the template again for the selected customer.');
            if(!Array.isArray(data.sections)||!Array.isArray(data.payments))throw new Error('Invalid template response.');
            state={sections:data.sections.map(row=>({...row,content:safeHTML(row.content)})),payments:data.payments};
            title.value=data.title||'TECHNICAL & FINANCIAL PROPOSAL';render();sync();
        }catch(exc){error(exc.message);}finally{loading=false;loadButton.disabled=kind.value!=='technical';}
    });
    document.addEventListener('pbw:sales-totals',event=>{untaxed=Number(event.detail?.untaxed)||0;currency=event.detail?.currency||'';totals();});
    document.addEventListener('click',event=>{
        if(kind.value!=='technical'||!event.target.closest('[data-sales-save]'))return;
        const invalid=Array.from(root.querySelectorAll('input')).find(field=>!field.checkValidity());
        if(loading||invalid){event.preventDefault();event.stopImmediatePropagation();if(invalid)invalid.reportValidity();else error('Wait for the selected template to finish loading before saving.');}
        sync(false);
    },true);
    render();toggle();
    return {get state(){return state;},get loading(){return loading;},safeHTML,render,sync,toggle};
}
function start(){const root=document.getElementById('pbw-proposal-draft-editor');if(root&&!root.dataset.mounted){root.dataset.mounted='1';mountProposalDraft(root);}}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
