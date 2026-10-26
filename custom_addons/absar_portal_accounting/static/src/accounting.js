/** @odoo-module **/
import { installDraftNavigation } from "./draft_navigation";
import { calculationRows, isEmptyDraftLine, decorateLineGrid } from "./line_grid";
import { createPurchaseUI } from "./purchase_ui";
import { openAnalyticDistribution } from "./analytic_editor";
(function () {
    'use strict';
    const BASE = '/my/employee/accounting';
    function mount(root) {
        root.classList?.add('absar-purchase-controls');
        let state = JSON.parse(root.dataset.boot), tab = 'lines', busy = false, revision = 0, previewTimer, overpaymentNotice = '', accountingNotice = '';
        const csrf = root.dataset.csrf;
        const isMove = () => ['bills', 'refunds', 'invoices', 'journals'].includes(state.kind);
        const isPlan = () => ['planned', 'planned-receipts'].includes(state.kind);
        const isBill = () => ['bills', 'refunds', 'invoices'].includes(state.kind);
        const money = n => Number(n || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        const lineKey = row => JSON.stringify([state.currency_id,state.partner_id,row.product_id,row.quantity,row.price_unit,row.discount,row.taxes_id,row.product_uom_id]);
        function drawLineAmounts() {
            for(const node of root.querySelectorAll('[data-line-amount]')) {
                const row=state.lines[Number(node.getAttribute('data-line-amount'))];
                node.textContent=row && Number.isFinite(Number(row.subtotal))?money(row.subtotal):'—';
            }
        }
        function el(tag, attrs = {}, children = []) {
            const node = document.createElement(tag);
            for (const [key, value] of Object.entries(attrs)) {
                if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
                else if (key === 'text') node.textContent = value;
                else if (key === 'class') node.className = value;
                else if (value !== false && value !== undefined && value !== null) node.setAttribute(key, value);
            }
            for (const child of children) if (child !== undefined && child !== null) node.append(child);
            return node;
        }
        let status, previewPending=false, previewError='', vendorSequence=0, closePicker, restoringFocus=false;
        if (typeof window !== 'undefined' && window.addEventListener) {
            window.addEventListener('resize',()=>closePicker?.());
            window.addEventListener('scroll',event=>{if(!event.target.closest?.('.aca-options'))closePicker?.();},true);
        }
        const resourceTitle = resource => ({partner:'Partners',product:'Products',account:'Accounts',journal:'Journals',currency:'Currencies',uom:'Units of Measure','product-category':'Product Categories','tax-grid':'Tax Grids',tax:'Taxes',po:'Purchase Orders',bank:'Bank Accounts','payment-term':'Payment Terms',analytic:'Analytic Accounts'}[resource] || resource.replaceAll('-',' '));
        function say(message, error = false) {
            if (status) {status.textContent = message; status.className = 'aca-status' + (error ? ' error' : '');}
        }
        async function api(operation, payload) {
            const body = new URLSearchParams({csrf_token: csrf, payload: JSON.stringify({company_id: state.company_id, kind: state.kind, ...payload})});
            const response = await fetch(BASE + '/api/' + operation, {method: 'POST', body, credentials: 'same-origin'});
            const data = await response.json();
            if (!data.ok) throw new Error(data.error || 'Operation failed.');
            return data.result;
        }
        function button(label, run, primary = false) {
            return el('button', {type: 'button', text: label, class: primary ? 'primary' : '', disabled: busy, onclick: run});
        }
        function label(name, control) {return el('label', {}, [el('span', {text: name}), control]);}
        function input(name, type = 'text', target = state, onChange) {
            const control = el(type === 'textarea' ? 'textarea' : 'input', {type: type === 'textarea' ? undefined : type,
                'aria-label': name, disabled: !state.editable, step: type === 'number' ? 'any' : undefined});
            control.value = target[name] ?? '';
            control.addEventListener('input', () => {
                target[name] = type === 'number' ? Number(control.value) : control.value;
                revision++;
                if (onChange) onChange(control.value);
                if (isMove()) {drawLineAmounts();schedulePreview();}
            });
            return control;
        }
        function field(title, name, type = 'text') {return label(title, input(name, type));}
        function select(title, name, values) {
            const node = el('select', {'aria-label': title, disabled: !state.editable});
            for (const [value, text] of values) {const o = el('option', {value, text}); o.selected = String(state[name] || '') === value; node.append(o);}
            node.addEventListener('change', () => {state[name] = node.value; revision++; render();});
            return label(title, node);
        }
        function ask(message, reason=false) {
            return new Promise(resolve=>{
                const previous=document.activeElement;
                const backdrop=el('div',{class:'aca-dialog-backdrop'}),dialog=el('div',{class:'aca aca-dialog',role:'dialog','aria-modal':'true','aria-label':reason?'Enter a reason':'Confirm action'});
                const finish=value=>{backdrop.remove();previous?.focus();resolve(value);};
                dialog.append(el('h3',{text:reason?'Enter a reason':'Confirm action'}),el('p',{text:message}));
                let input;
                if(reason){input=el('textarea',{'aria-label':'Reason',placeholder:'Enter the reason…'});dialog.append(input);}
                dialog.append(button('Cancel',()=>finish(reason?null:false)),button('Continue',()=>{if(reason&&!input.value.trim()){input.focus();return;}finish(reason?input.value.trim():true);},true));
                dialog.addEventListener('keydown',event=>{if(event.key==='Escape')finish(reason?null:false);});
                backdrop.append(dialog);document.body.append(backdrop);if(input)input.focus();
            });
        }
        function searchMore(resource, query, choose) {
            const backdrop=el('div',{class:'aca-dialog-backdrop'}),dialog=el('div',{class:'aca aca-dialog',role:'dialog','aria-modal':'true','aria-label':'Search '+resourceTitle(resource)});
            const search=el('input',{type:'search','aria-label':'Search records',placeholder:'Search by name or reference…'});search.value=query||'';
            const list=el('div',{class:'aca-search-results'}),pager=el('div',{class:'aca-pager'});let offset=0,sequence=0;
            async function load(){const seq=++sequence;list.replaceChildren(el('p',{text:'Searching…'}));try{
                const rows=await api('options',{resource,q:search.value,partner_id:state.partner_id,offset,limit:31});if(seq!==sequence)return;
                list.replaceChildren();for(const row of rows.slice(0,30))list.append(button(row.name,()=>{backdrop.remove();choose(row);revision++;}));
                if(!rows.length)list.append(el('p',{text:'No matching records'}));
                pager.replaceChildren();if(offset)pager.append(button('Previous',()=>{offset=Math.max(0,offset-30);load();}));
                pager.append(el('span',{text:'Page '+(offset/30+1)}));if(rows.length>30)pager.append(button('Next',()=>{offset+=30;load();}));
            }catch(error){list.replaceChildren(el('p',{text:error.message}));}}
            search.addEventListener('input',()=>{offset=0;load();});
            dialog.addEventListener('keydown',event=>{if(event.key==='Escape')backdrop.remove();});
            const head=el('div',{class:'aca-dialog-head'});head.append(el('h3',{text:'Search '+resourceTitle(resource)}),button('Close',()=>backdrop.remove()));
            dialog.className+=' aca-search-dialog';dialog.append(head,search,list,pager);backdrop.append(dialog);document.body.append(backdrop);load();search.focus();
        }
        async function supplierDefaults(partnerId) {
            const sequence=++vendorSequence;
            try {const defaults=await api('defaults',{partner_id:partnerId});if(sequence!==vendorSequence||state.partner_id!==partnerId)return;
                state.currency_id=defaults.currency_id;state.currency_name=defaults.currency_name;state.selections.currency_id=defaults.selections.currency_id;
                if(!state.journal_id){state.journal_id=defaults.journal_id;state.selections.journal_id=defaults.selections.journal_id;}
                state.invoice_payment_term_id=defaults.invoice_payment_term_id;state.selections.invoice_payment_term_id=defaults.selections.invoice_payment_term_id;
                state.partner_bank_id=false;state.selections.partner_bank_id=null;revision++;render();schedulePreview();
            }catch(error){say(error.message,true);}
        }
        function picker(resource, selected, choose, disabled = !state.editable) {
            let requestId = 0, timer, active=-1, choices=[], latestLoad=null, queued=false;
            const box = el('div', {class: 'aca-picker'});
            const control = el('input', {type: 'text', role: 'combobox', 'aria-label': resource + ' search',
                autocomplete: 'off', 'aria-expanded': 'false', disabled, placeholder: disabled?'':'Search ' + resource + '…'});
            control.value = selected?.name || '';
            const options = el('div', {class: 'aca-options', role: 'listbox', hidden: true});
            options.setAttribute('popover','manual');
            const close=()=>{++requestId;clearTimeout(timer);if(typeof options.hidePopover==='function' && options.matches(':popover-open'))options.hidePopover();options.hidden=true;control.setAttribute('aria-expanded','false');};
            const show=()=>{
                if(closePicker!==close)closePicker?.();closePicker=close;
                options.hidden=false;
                if(control.getBoundingClientRect){
                    const rect=control.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
                    const width=Math.min(Math.max(rect.width,300),vw-24),below=vh-rect.bottom-12,above=rect.top-12;
                    const up=below<180 && above>below,height=Math.min(280,Math.max(100,up?above:below));
                    Object.assign(options.style,{position:'fixed',left:Math.max(12,Math.min(rect.left,vw-width-12))+'px',top:(up?Math.max(12,rect.top-height-4):rect.bottom+4)+'px',width:width+'px',maxHeight:height+'px',margin:'0',right:'auto',bottom:'auto'});
                }
                if(typeof options.showPopover==='function'&&!options.matches(':popover-open'))options.showPopover();
                control.setAttribute('aria-expanded','true');
            };
            async function commit(row, advance=false) {
                const cell=control.closest?.('[data-grid-column]'), line=control.closest?.('[data-grid-row]');
                const position=cell&&line?[Number(line.dataset.gridRow),Number(cell.dataset.gridColumn)]:null;
                selected=row;control.value=row.name;close();
                try {await choose(row);revision++;if(advance&&position)moveGrid(...position,1);}
                catch(error){say(error.message,true);}
            }
            function load(){queued=false;latestLoad=loadRows();return latestLoad;}
            async function loadRows() {
                const seq = ++requestId;
                try {
                    const rows = await api('options', {resource, q: control.value, partner_id: state.partner_id});
                    if (seq !== requestId || !box.isConnected) return;
                    choices=rows.slice(0,30);active=-1;options.replaceChildren(); show();
                    if (!rows.length) options.append(el('div', {class: 'aca-mini', text: 'No matching records'}));
                    for (const row of rows.slice(0,30)) options.append(el('button', {type: 'button', role: 'option', text: row.name,
                        onmousedown: event => event.preventDefault(), onclick: () => commit(row)}));
                    options.append(button('Search More…',()=>{close();searchMore(resource,control.value,row=>commit(row));}));
                    if(resource==='product'&&selected?.id)options.append(button(state.kind==='invoices'?'Open Product…':'Open / Edit Product…',()=>{
                        close();productForm(selected.id,'',row=>commit(row));
                    }));
                    if(resource==='product'&&!disabled&&state.kind!=='invoices')options.append(button('Create and Edit…',()=>{
                        const name=control.value;close();productForm(null,name,row=>commit(row));
                    }));
                } catch (error) {say(error.message, true);}
            }
            control.addEventListener('focus', () => {if(!restoringFocus){control.value = ''; load();}});
            control.addEventListener('input', () => {++requestId;choices=[];active=-1;queued=true;clearTimeout(timer);timer=setTimeout(load,180);});
            box.addEventListener('focusout', () => setTimeout(()=>{if(!box.contains(document.activeElement)){close();requestId++;control.value=selected?.name||'';}},100));
            control.addEventListener('keydown', async event => {
                if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();latestLoad=null;queued=false;choices=[];control.value=selected?.name||'';return;}
                if(!options.hidden&&['ArrowDown','ArrowUp'].includes(event.key)){
                    event.preventDefault();event.stopPropagation();
                    active=Math.max(0,Math.min(choices.length-1,active+(event.key==='ArrowDown'?1:-1)));
                    options.querySelectorAll('[role="option"]').forEach((node,index)=>node.setAttribute('aria-selected',index===active));
                }
                if(event.key==='Enter'&&(queued||latestLoad||!options.hidden)){
                    event.preventDefault();event.stopPropagation();
                    if(queued){clearTimeout(timer);await load();}else if(latestLoad)await latestLoad;
                    if(!box.isConnected||document.activeElement!==control)return;
                    if(choices.length)await commit(choices[Math.max(0,active)],true);
                    else say('Choose a matching record, or use Create and Edit for a new product.',true);
                }
            });
            box.append(control, options);
            if (!disabled && selected?.id) {const clear=button('×',()=>{choose({id:false,name:''});revision++;render();});clear.setAttribute('aria-label','Clear '+resource);clear.setAttribute('title','Clear selection');box.append(clear);}
            return box;
        }
        function relation(title, name, resource, onPick) {
            return label(title, picker(resource, state.selections[name], row => {
                state[name] = row.id; state.selections[name] = row;
                if(name==='currency_id')state.currency_name=row.name;
                if(name==='partner_id' && isBill())supplierDefaults(row.id);
                if (onPick) onPick(row);
                render(); if (isMove()) schedulePreview();
            }));
        }
        function multiple(title, name, resource) {
            state[name] ||= []; state.selections[name] ||= [];
            const box = el('div');
            box.append(label(title, picker(resource, null, row => {
                if (!state[name].includes(row.id)) {state[name].push(row.id); state.selections[name].push(row);}
                if (name === 'purchase_order_ids' && state.kind === 'payments' && !state.allocations.some(a => a.purchase_order_id === row.id))
                    state.allocations.push({purchase_order_id: row.id, name: row.name, amount: state[name].length === 1 ? Number(state.amount || 0) : 0});
                render();
            })));
            const pills = el('div', {class: 'aca-pills'});
            for (const row of state.selections[name]) {
                const pill = el('span', {class: 'aca-pill', text: row.name});
                if (state.editable) pill.append(button('×', () => {
                    state[name] = state[name].filter(id => id !== row.id);
                    state.selections[name] = state.selections[name].filter(r => r.id !== row.id);
                    if (name === 'purchase_order_ids') state.allocations = state.allocations.filter(a => a.purchase_order_id !== row.id);
                    revision++; render();
                }));
                pills.append(pill);
            }
            box.append(pills); return box;
        }
        function analyticText(target, key='analytic_distribution') {
            return Object.entries(target[key]||{}).map(([ids,percent])=>{
                const name=String(ids).split(',').map(id=>state.analytic_names?.[id]||'Analytic '+id).join(' / ');
                return name+(Number(percent)===100?'':' ('+percent+'%)');
            }).join(', ');
        }
        function analytic(target, key = 'analytic_distribution') {
            if(!state.editable&&!Object.keys(target[key]||{}).length)return el('span');
            const control = button(analyticText(target,key) || 'Set distribution', () => {
                const labels={...(state.analytic_labels||{})};
                for(const [id,name] of Object.entries(state.analytic_names||{}))labels[id]||={id:Number(id),label:name};
                const ui=createPurchaseUI({root,companyId:state.company_id,readonly:!state.editable,
                    post:async(path,payload)=>{
                        const rows=await api('options',{resource:'analytic',q:payload.q,offset:payload.offset,limit:31});
                        return {items:rows.slice(0,30).map(row=>({...row,label:row.name})),more:rows.length>30};
                    }});
                openAnalyticDistribution({ui,distribution:target[key]||{},labels,readonly:!state.editable,
                    onApply:(distribution,labels)=>{
                        target[key]=distribution;state.analytic_labels={...(state.analytic_labels||{}),...labels};
                        state.analytic_names||={};for(const [id,item] of Object.entries(labels))state.analytic_names[id]=item.label;
                        revision++;render();schedulePreview();
                    }});

            });
            control.className='aca-analytic-control';control.setAttribute('title',analyticText(target,key)||'Set distribution');
            control.setAttribute('aria-label','Analytic distribution');return control;
        }
        function schedulePreview() {
            clearTimeout(previewTimer);previewPending=true;drawTotals();
            previewTimer = setTimeout(preview, 250);
        }
        async function preview() {
            if (!state.editable || !isMove() || busy) return;
            const lines=calculationRows(state.lines);
            if(!lines.length){previewPending=false;previewError='';state.untaxed=0;state.tax=0;state.total=0;state.journal_items=[];drawLineAmounts();drawTotals();return;}
            const missing=[];
            if(!state.journal_id)missing.push('journal');
            if(isBill()&&!state.partner_id)missing.push(state.kind==='invoices'?'customer':'vendor');
            if(lines.some(row=>!['line_section','line_note'].includes(row.display_type)&&!row.account_id))missing.push('line account');
            if(missing.length){previewPending=false;previewError=missing.length?'Choose '+missing.join(', ')+' to calculate totals.':'Add a line to calculate totals.';drawLineAmounts();drawTotals();say(previewError);return;}
            previewError='';
            const seq = revision;
            const totals = root.querySelector('[data-totals]');
            if (totals) totals.dataset.pending = 'true';
            try {
                const result = await api('preview', {...state,lines});
                if (seq !== revision) return;
                previewPending=false;previewError='';state.untaxed = result.untaxed; state.tax = result.tax; state.total = result.total;
                state.currency_name=result.currency;if(result.journal_items)state.journal_items=result.journal_items;
                const journalHost=root.querySelector('[data-journal-items]');if(journalHost)journalHost.replaceChildren(journalItemsTable().querySelector('table'));
                (result.line_amounts||[]).forEach((value,index)=>{if(lines[index]&&state.lines.includes(lines[index])){lines[index].subtotal=value;lines[index]._amountKey=lineKey(lines[index]);}});
                drawLineAmounts();drawTotals(); say('');
            } catch (error) {if (seq === revision) {previewPending=false;previewError=error.message;drawLineAmounts();drawTotals();say('Totals unavailable: '+error.message,true);}}
        }
        function drawTotals() {
            const node = root.querySelector('[data-totals]'); if (!node) return;
            node.replaceChildren(); node.dataset.pending = String(previewPending);
            if(previewError)node.append(el('p',{class:'aca-mini',text:previewError}));
            else if(previewPending)node.append(el('p',{class:'aca-mini',text:'Updating…'}));
            if (state.kind === 'journals') {
                const debit = state.lines.reduce((n, l) => n + Number(l.debit || 0), 0);
                const credit = state.lines.reduce((n, l) => n + Number(l.credit || 0), 0);
                for (const [title, value] of [['Debit', debit], ['Credit', credit], ['Difference', debit - credit]]) node.append(el('div', {}, [el('span', {text: title}), el('strong', {text: money(value)})]));
            } else {
                for (const [title, value] of [['Untaxed Amount', state.untaxed], ['Taxes', state.tax], ['Total', state.total]]) node.append(el('div', {}, [el('span', {text: title}), el('strong', {text: money(value) + ' ' + (state.currency_name || state.currency || '')})]));
            }
        }
        let operationJob=null;
        function run(...args){if(operationJob)return operationJob;const job=runOperation(...args);operationJob=job;job.then(()=>{operationJob=null;},()=>{operationJob=null;});return job;}
        async function runOperation(operation, payload) {
            if (busy) return false;
            if(operation==='save'&&payload.submit&&isBill()&&!payload.invoice_date){say('Set the invoice/bill date before submitting for approval.',true);return;}
            if(operation==='save'&&isMove())payload={...payload,lines:calculationRows(payload.lines||[])};
            busy = true; clearTimeout(previewTimer); root.querySelectorAll('button').forEach(b => b.disabled = true); say('Working…');
            try {
                const result = await api(operation, payload);
                if (result.redirect) {savedDraft=draftSignature();window.location.assign(result.redirect); return true;}
                state = result; previewError=''; revision++;savedDraft=draftSignature();
                for(const row of state.lines||[])if(row.subtotal!==undefined)row._amountKey=lineKey(row);
                if (state.id) history.replaceState(null, '', BASE + '/' + state.kind + '/' + state.id + '?company_id=' + state.company_id);
                busy = false; render();savedDraft=draftSignature(); say('Saved successfully.');return true;
            } catch (error) {
                busy = false;
                if(error.message.startsWith('PO OVERPAYMENT:'))overpaymentNotice=error.message;
                if(error.message.startsWith('ACCOUNTING WARNING:'))accountingNotice=error.message;
                render(); say(error.message, true);return false;
            }
        }
        function action(name, extra = {}) {return run('action', {id: state.id, version: state.version, action: name, ...extra});}
        function reviewDialog(returning = false) {
            const backdrop = el('div', {class: 'aca-dialog-backdrop'}), box = el('div', {class: 'aca aca-dialog', role: 'dialog', 'aria-modal': 'true'});
            box.append(el('h3', {text: returning ? 'Return for correction' : state.can_post ? 'Post document' : 'Approve and post'}));
            box.append(el('p', {text: returning ? 'Explain what needs to change.' : 'This posts the document using the existing accounting workflow.'}));
            const comment = el('textarea', {'aria-label': 'Review comment'}); box.append(comment);
            let abnormal;
            if(!returning && (state.warnings || accountingNotice)){
                box.append(el('div',{class:'aca-alert',text:accountingNotice || state.warnings}));
                abnormal=el('input',{type:'checkbox'});
                box.append(label('I reviewed the accounting warning above and approve this posting.',abnormal));
            }
            let overpayment;
            if (!returning && state.kind === 'payments' && overpaymentNotice) {
                box.append(el('div',{class:'aca-alert',text:overpaymentNotice}));
                overpayment = el('input', {type: 'checkbox'});
                box.append(label('I explicitly approve the PO overpayment detailed above.', overpayment));
            }
            box.append(button('Cancel', () => backdrop.remove()), button(returning ? 'Return' : state.can_post ? 'Post' : 'Approve & Post', () => {
                if (returning && !comment.value.trim()) {comment.focus(); return;}
                backdrop.remove();
                const flags={comment:comment.value,confirm_overpayment:overpayment?.checked===true,confirm_abnormal:abnormal?.checked===true};
                if (!returning && state.can_post) run('save',{...state,...flags,submit:false,post:true});
                else action(returning?'return':'post',flags);
            }, true));
            backdrop.append(box); document.body.append(backdrop); comment.focus();
        }
        function actions() {
            const box = el('div', {class: 'aca-actions absar-document-actions'});
            if (state.editable) {
                box.append(button('Save Draft', () => run('save', {...state, submit: false, post:false}), true),
                    el('a',{text:'Cancel',class:'btn btn-outline-secondary','data-draft-cancel':'1',href:BASE+'/'+state.kind+'?company_id='+state.company_id}));
                if (state.can_post && !isPlan()) box.append(button('Post',()=>{if(state.warnings || accountingNotice || overpaymentNotice) reviewDialog(); else run('save',{...state,submit:false,post:true});},true));
                else if (state.kind !== 'planned-receipts' && (isPlan() || state.review_required !== false)) box.append(button(isPlan() ? 'Submit to CEO' : 'Submit for Approval', () => run('save', {...state, submit: true, post:false})));
                if (state.id && !isPlan()) box.append(button('Cancel Draft', async () => {
                    if (await ask('Cancel this draft document?')) action('cancel');
                }));
            }
            if (state.can_review && !isPlan()) box.append(button('Approve & Post', () => reviewDialog(), true), button('Return for Correction', () => reviewDialog(true)));
            if (state.id && ['payments', 'receipts'].includes(state.kind)) {
                if (state.editable) box.append(button('Find Matching ' + (state.kind === 'payments' ? 'Bills' : 'Invoices'), () => action('find')));
                if (state.state === 'posted' && (state.roles.approver || state.roles.direct)) box.append(button('Reconcile', () => action('reconcile')), button('Unreconcile', async () => {
                    if (await ask('Remove only the reconciliations managed by this voucher?')) action('unreconcile');
                }));
            }
            if (state.id && ['bills', 'refunds', 'invoices', 'journals', 'payments', 'receipts'].includes(state.kind)) box.append(el('a', {text: state.kind==='invoices'?'Print Tax Invoice':'Print PDF', class: 'aca-primary', target: '_blank', rel: 'noopener', href: BASE + '/' + state.kind + '/' + state.id + '/print?company_id=' + state.company_id}));
            if(state.kind==='invoices' && state.id){
                if(state.edi_state)box.append(el('span',{class:'aca-mini',text:'E-Invoicing: '+state.edi_state}));
                if(state.edi_error)box.append(el('div',{class:'aca-alert',text:state.edi_error}));
                if(state.can_process_edi)box.append(button('Process ZATCA',async()=>{if(await ask('Submit this posted invoice through the configured Saudi e-invoicing service?'))action('process-edi');}));
            }
            if(state.id && (isMove() || (['payments','receipts'].includes(state.kind) && state.state==='posted'))) box.append(el('a',{text:'Print Journal Entry',class:'aca-print-link',target:'_blank',rel:'noopener',href:BASE+'/'+state.kind+'/'+state.id+'/print?company_id='+state.company_id+'&journal_entry=1'}));
            if (state.id && state.kind === 'bills' && state.state === 'posted' && state.roles.preparer && state.balance_due > 0) box.append(el('a', {text:'Create Payment Voucher',class:'aca-primary',href:BASE+'/payments/new?company_id='+state.company_id+'&bill_id='+state.id}));
            if (state.id && !isPlan() && (state.roles.preparer || state.roles.approver) && ['posted','cancel'].includes(state.state)) {
                if (state.portal_accounting_reset_pending) box.append(el('span',{class:'aca-mini',text:'Reset permission requested — awaiting internal review'}));
                else box.append(button('Request Reset to Draft', async () => {
                    const comment=await ask('Why is a reset needed? The document stays posted until an authorized internal user completes the existing reset approval.',true);
                    if(comment?.trim())action('request-reset',{comment});
                }));
            }
            if (isPlan() && state.id) {
                if(state.roles.preparer&&!state.editable&&state.state!=='executed'){
                    if(state.reset_request_pending)box.append(el('span',{class:'aca-mini',text:'Reset approval pending'}));
                    else box.append(button('Request Reset to Draft',async ()=>{
                        if(await ask('Request approval from an existing Payment Execution Manager to reset this movement?'))action('request-reset');
                    }));
                }
                if (state.roles.preparer && (state.state === 'executed' || state.kind === 'planned-receipts')) box.append(button('Create Voucher', () => action('create-voucher')));
                if (state.is_ceo && !state.run_id) box.append(button('Add to Weekly Plan', () => planDialog()));
                if (state.is_ceo && state.kind === 'planned' && ['pending', 'held'].includes(state.review)) {
                    box.append(button('Approve Payment', () => planDialog(true), true));
                    for (const [name, title] of [['hold', 'Hold'], ['reject', 'Reject']]) box.append(button(title, async () => {
                        const comment = await ask('CEO comment',true); if (comment !== null) action(name, {comment});
                    }));
                }
            }
            return box;
        }
        function planDialog(approval = false) {
            const backdrop = el('div', {class: 'aca-dialog-backdrop'}), box = el('div', {class: 'aca aca-dialog', role: 'dialog', 'aria-modal': 'true'});
            let selected, amount;
            box.append(el('h3', {text: approval ? 'Approve Payment' : 'Add to Weekly Plan'}));
            if (approval) {
                amount = el('input', {type: 'number', step: 'any', 'aria-label': 'Approved amount'}); amount.value = state.forecast_amount; box.append(label('Approved amount', amount));
            } else box.append(label('Weekly plan', picker('run', null, row => {selected = row;}, false)));
            const comment = el('textarea', {'aria-label': 'CEO comment'}); if (approval) box.append(comment);
            box.append(button('Cancel', () => backdrop.remove()), button('Confirm', () => {
                if (!approval && !selected) return;
                backdrop.remove(); action(approval ? 'approve' : 'add-plan', approval ? {approved_amount: Number(amount.value), comment: comment.value} : {run_id: selected.id});
            }, true));
            backdrop.append(box); document.body.append(backdrop);
        }
        function headerFields() {
            const grid = el('div', {class: 'aca-grid'});
            if (state.kind === 'journals') {
                grid.append(field('Accounting Date', 'date', 'date'), relation('Journal', 'journal_id', 'journal'), field('Reference', 'ref'), field('Payment Reference', 'payment_reference'), relation('Currency', 'currency_id', 'currency'));
            } else if (isBill()) {
                grid.append(relation(state.kind==='invoices'?'Customer':'Vendor', 'partner_id', 'partner'), field(state.kind==='invoices'?'Reference':'Bill Reference', 'ref'), field(state.kind==='invoices'?'Invoice Date':'Bill Date', 'invoice_date', 'date'),
                    field('Accounting Date', 'date', 'date'), relation('Journal', 'journal_id', 'journal'), relation('Currency', 'currency_id', 'currency'),
                    relation('Payment Terms', 'invoice_payment_term_id', 'term'), field('Due Date', 'invoice_date_due', 'date'),
                    field('Payment Reference', 'payment_reference'), relation('Recipient Bank', 'partner_bank_id', 'bank'));
                if (state.editable && state.kind!=='invoices') grid.append(label('Auto-complete from Purchase Order', picker('po', null, async row => {
                    try {
                        const result = await api('po-lines', {po_id: row.id});
                        if (state.lines.length && !await ask('Replace the current bill lines with this PO’s billable lines?')) return;
                        Object.assign(state, result);
                        state.selections.partner_id = {id: result.partner_id, name: result.partner_name};
                        state.selections.currency_id = {id: result.currency_id, name: result.currency_name};
                        revision++; render(); schedulePreview();
                    } catch (error) {say(error.message, true);}
                })));
            } else if (isPlan()) {
                grid.append(field('Description', 'name'), relation('Partner', 'partner_id', 'partner'), relation('Category', 'category_id', 'category'),
                    field('Forecast Amount', 'forecast_amount', 'number'), relation('Project', 'project_id', 'project'), relation('Journal', 'journal_id', 'journal'),
                    relation('Account', 'account_id', 'account'), select('Transaction Type', 'transaction_type', [['supplier','Supplier / Subcontractor'],['expense','Expense'],['payroll','Payroll / Manpower'],['cash','Cash Withdrawal / Deposit'],['transfer','Journal Transfer'],['loan','Loan / Financing'],['customer','Customer Collection'],['revenue','Sales / Revenue'],['other','Other']]),
                    select('Priority', 'priority', [['0','Low'],['1','Normal'],['2','High'],['3','Urgent']]),
                    select('Funding Status', 'funding_status', [['funded','Funded'],['partial','Partially Funded'],['unfunded','Not Funded']]));
                grid.append(el('div', {text: 'Weekly Plan: ' + (state.selections.run_id?.name || 'Not added')}),
                    el('div', {text: 'CEO Approved Amount: ' + money(state.approved_amount)}), el('div', {text: 'Actual Amount: ' + money(state.actual_amount)}));
            } else {
                const payment = state.kind === 'payments';
                grid.append(field('Date', 'date', 'date'), relation(payment ? 'Pay To' : 'Received From', 'partner_id', 'partner'),
                    field('Amount', 'amount', 'number'), label('Currency',el('input',{type:'text',value:state.currency_name || state.currency,disabled:true})),
                    relation(payment ? 'Source Journal' : 'Deposit To', 'journal_id', 'journal'),
                    relation(payment ? 'Account' : 'Income / Receivable Account', 'account_id', 'account'),
                    select(payment ? 'Payment Method' : 'Receipt Method', payment ? 'payment_method' : 'receipt_method',
                        [['cash','Cash'],['cheque','Cheque'],['bank_transfer','Bank Transfer'],...(payment ? [['journal_transfer','Journal Transfer']] : [])]),
                    label('Analytic Distribution', analytic(state)));
            }
            return grid;
        }
        function blankLine() {const taxes=isBill()?(state.default_taxes||[]):[];return {name:'',quantity:1,price_unit:0,discount:0,debit:0,credit:0,taxes_id:taxes.map(t=>t.id),tax_names:taxes.map(t=>({...t})),_defaultTaxes:taxes.map(t=>t.id),analytic_distribution:{}};}
        function gridControl(row,column) {return root.querySelector(`[data-grid-row="${row}"] [data-grid-column="${column}"] [data-grid-entry]`);}
        function moveGrid(row,column,direction) {
            let cells=[...root.querySelectorAll('[data-grid-row] [data-grid-entry]')].filter(n=>!n.disabled);
            const current=gridControl(row,column),index=cells.indexOf(current);
            if(index<0)return;
            let next=cells[index+direction];
            if(!next&&direction>0&&state.editable&&state.lines.length<200&&!isEmptyDraftLine(state.lines.at(-1))){
                state.lines.push(blankLine());revision++;render();
                next=gridControl(state.lines.length-1,0);
            }
            if(next){restoringFocus=true;next.focus();restoringFocus=false;next.select?.();next.scrollIntoView?.({block:'nearest',inline:'nearest'});}
        }
        async function productForm(productId, initialName='', onSaved=()=>{}) {
            try {
                const data=await api(productId?'product-read':'product-defaults',{id:productId});
                const readonly=!state.editable||!data.can_edit, values={...data,name:data.name||initialName};
                for(const key of ['categ_id','uom_id','uom_po_id','property_account_expense_id'])values[key]=data[key]?.id||false;
                const previous=document.activeElement,backdrop=el('div',{class:'aca-dialog-backdrop'}),dialog=el('div',{class:'aca aca-dialog',role:'dialog','aria-modal':'true','aria-label':productId?'Product form':'Create product'});
                const close=()=>{backdrop.remove();previous?.isConnected&&previous.focus();};
                dialog.append(el('h3',{text:productId?'Product: '+data.name:'Create Product'}));
                if(data.shared&&state.kind!=='invoices')dialog.append(el('p',{class:'aca-mini',text:'General details apply across companies. The expense account is saved for the selected company.'}));
                const grid=el('div',{class:'aca-grid'}),message=el('p',{role:'status',class:'aca-status error'});
                for(const [title,key,type] of [['Product Name','name','text'],['Internal Reference','default_code','text'],['Barcode','barcode','text'],[state.kind==='invoices'?'Sales Price':'Cost','standard_price','number'],[state.kind==='invoices'?'Sales Description':'Purchase Description','description_purchase','text']]){
                    const control=input(key,type,values);control.disabled=readonly;grid.append(label(title,control));
                }
                for(const [title,key,choices] of [['Product Type','type',[['consu','Goods'],['service','Service']]],['Bill Control Policy','purchase_method',[['receive','On received quantities'],['purchase','On ordered quantities']]]]){
                    const control=el('select',{'aria-label':title,disabled:readonly});
                    for(const [value,text] of choices)control.append(el('option',{value,text}));control.value=values[key];
                    control.addEventListener('change',()=>{values[key]=control.value;});grid.append(label(title,control));
                }
                const tracked=el('input',{type:'checkbox',disabled:readonly,'aria-label':'Track Inventory'});tracked.checked=Boolean(values.is_storable);
                tracked.addEventListener('change',()=>{values.is_storable=tracked.checked;});grid.append(label('Track Inventory (Goods)',tracked));
                for(const [title,key,resource] of [['Category','categ_id','product-category'],['Unit of Measure','uom_id','uom'],['Purchase Unit','uom_po_id','uom'],[state.kind==='invoices'?'Income Account':'Expense Account','property_account_expense_id','account']])
                    grid.append(label(title,picker(resource,data[key],row=>{values[key]=row.id;},readonly)));
                grid.append(el('p',{class:'aca-mini',text:(state.kind==='invoices'?'An empty income account uses the category account. ':'An empty expense account uses the category account. ')+(data.category_expense_account||'')}));
                const taxes=new Map((data.supplier_taxes||[]).map(t=>[t.id,t])),taxBox=el('div'),chips=el('div',{class:'aca-pills'});
                function drawTaxes(){chips.replaceChildren();for(const tax of taxes.values()){
                    const chip=el('span',{class:'aca-pill',text:tax.name});if(!readonly)chip.append(button('×',()=>{taxes.delete(tax.id);drawTaxes();}));chips.append(chip);}}
                taxBox.append(picker('tax',null,row=>{taxes.set(row.id,row);drawTaxes();},readonly),chips);drawTaxes();grid.append(label(state.kind==='invoices'?'Sales Taxes':'Purchase Taxes',taxBox));
                const save=button(productId?'Save Product':'Create and Add',async()=>{
                    save.disabled=true;message.textContent='';
                    try{const selected=await api(productId?'product-update':'product-create',{...values,id:productId,supplier_taxes_id:[...taxes.keys()]});
                        close();await onSaved(selected);
                    }catch(error){message.textContent=error.message;save.disabled=false;}
                },true);
                dialog.append(grid,message,button(readonly?'Close':'Discard',close));if(!readonly)dialog.append(save);
                dialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.stopPropagation();close();}});
                backdrop.append(dialog);document.body.append(backdrop);grid.querySelector('input')?.focus();
            }catch(error){say(error.message,true);}
        }
        function selectProduct(row, selected) {
            const editing=selected.product_updated&&row.product_id===selected.id;
            row.product_id=selected.id;row.product_name=selected.name;
            row.account_id=selected.account_id;row.account_name=selected.account_name;
            if(!editing){row.name=state.kind==='invoices'?(selected.description||selected.name):selected.name;if(state.kind==='invoices'&&selected.price_unit!==undefined)row.price_unit=selected.price_unit;row.product_uom_id=selected.product_uom_id;row.uom_name=selected.uom_name;
                const taxes=selected.tax_ids?.length?selected.tax_ids:(state.default_taxes||[]);row.taxes_id=taxes.map(t=>t.id);row.tax_names=taxes.map(t=>({...t}));}
            revision++;render();schedulePreview();
        }
        function lineTags(row, grids=false) {
            const ids=grids?'tax_tag_ids':'taxes_id', names=grids?'grid_names':'tax_names';
            const box=el('div',{class:'aca-line-tags'});
            if(state.editable){const add=picker(grids?'tax-grid':'tax',null,selected=>{
                row[ids]||=[];row[names]||=[];
                if(!row[ids].includes(selected.id)){row[ids].push(selected.id);row[names].push(selected);}
                revision++;render();schedulePreview();
            });add.className+=' aca-tag-add';add.querySelector('input').setAttribute('placeholder','+');add.querySelector('input').setAttribute('aria-label',grids?'Add tax grid':'Add tax');box.append(add);}
            for(const item of row[names]||[]){const chip=el('span',{class:'aca-pill',text:item.name});
                if(state.editable)chip.append(button('×',()=>{row[ids]=row[ids].filter(id=>id!==item.id);row[names]=row[names].filter(t=>t.id!==item.id);revision++;render();schedulePreview();}));
                box.append(chip);
            }
            return box;
        }
        function lineTable() {
            const journal=state.kind==='journals',wrap=el('div',{class:'aca-table-wrap'}),table=el('table',{class:'aca-table aca-lines aca-grid-lines '+(journal?'aca-journal-lines':'aca-invoice-lines')});
            const titles=journal?['Account','Partner','Label','Analytic Distribution','Taxes','Debit','Credit','Tax Grids','']:
                ['Product','Account','Analytic','Quantity','Price','Disc.%','Taxes','Amount','Company Currency',''];
            table.append(el('thead',{},[el('tr',{},titles.map(text=>el('th',{text})))]));
            const body=el('tbody');
            state.lines.forEach((row,index)=>{
                const tr=el('tr',{'data-grid-row':index,class:'aca-line-row'});let column=0;
                const td=(child,cls='',entry=true)=>{
                    const cell=el('td',{'data-grid-column':column++,class:cls},[child]);
                    if(entry){const control=child.matches?.('input,select,button')?child:child.querySelector('input,select,button');
                        if(control&&!control.disabled)control.setAttribute('data-grid-entry','true');}
                    tr.append(cell);return cell;
                };
                if(['line_section','line_note'].includes(row.display_type)){
                    const cell=td(input('name','text',row),'aca-section');cell.colSpan=titles.length-1;
                }else{
                    if(!journal){const product=el('div',{class:'aca-product-cell',title:row.name||''},[picker('product',{id:row.product_id,name:row.product_name||row.name},selected=>selectProduct(row,selected))]);
                        if(row.product_id){const open=button('↗',()=>productForm(row.product_id,'',selected=>selectProduct(row,selected)));
                            open.setAttribute('aria-label','Open product '+(index+1));open.setAttribute('title','Open product');product.append(open);}
                        const description=input('name','textarea',row);description.className='aca-line-description';description.rows=1;description.setAttribute('aria-label','Line description');
                        td(el('div',{class:'aca-product-description'},[product,description]),'desc');}
                    td(picker('account',{id:row.account_id,name:row.account_name},selected=>{
                        row.account_id=selected.id;row.account_name=selected.name;revision++;render();schedulePreview();}),'account');
                    if(journal){
                        td(picker('partner',{id:row.partner_id,name:row.partner_name},selected=>{row.partner_id=selected.id;row.partner_name=selected.name;revision++;render();}));
                        td(input('name','text',row),'aca-description');
                    }
                    td(analytic(row),'aca-analytic-cell');
                    if(journal){
                        td(lineTags(row),'aca-tax-cell');
                        for(const key of ['debit','credit'])td(input(key,'number',row,drawTotals),'aca-money');
                        td(lineTags(row,true),'aca-tax-grid-cell');
                    }else{
                        td(input('quantity','number',row));
                        for(const key of ['price_unit','discount'])td(input(key,'number',row));
                        td(lineTags(row),'aca-tax-cell');
                        td(el('span',{'data-line-amount':index,text:Number.isFinite(Number(row.subtotal))?money(row.subtotal):'—'}),'aca-money',false);
                        td(el('span',{text:state.company_currency_name||'',title:'Company currency'}),'aca-company-currency',false);
                    }
                }
                const controls=el('div',{class:'aca-row-actions'});
                controls.append(button('⋯',()=>lineDetails(row,journal)));
                if(state.editable)controls.append(button('×',()=>{state.lines.splice(index,1);revision++;render();schedulePreview();}));
                for(const control of controls.children){const title=(control.textContent==='↑'?'Move line up':control.textContent==='↓'?'Move line down':control.textContent==='×'?'Remove line':'Line details')+' '+(index+1);control.setAttribute('aria-label',title);control.setAttribute('title',title);}
                td(controls,'aca-line-tools',false);body.append(tr);
            });
            table.addEventListener('keydown',event=>{
                if(event.key!=='Enter'||event.defaultPrevented||event.isComposing||(event.ctrlKey&&event.target.tagName==='TEXTAREA'))return;
                const control=event.target.closest('[data-grid-entry],.aca-line-description');if(!control)return;
                const cell=control.closest('[data-grid-column]'),row=control.closest('[data-grid-row]');
                event.preventDefault();moveGrid(Number(row.dataset.gridRow),Number(cell.dataset.gridColumn),event.shiftKey?-1:1);
            });
            table.append(body);decorateLineGrid(table,{editor:journal?'journal':'invoice',editable:state.editable&&!busy,entrySelector:'[data-grid-entry]',onAppend:()=>{if(isEmptyDraftLine(state.lines.at(-1)))return false;moveGrid(state.lines.length-1,journal?7:6,1);},onReorder:(from,to)=>{const [line]=state.lines.splice(from,1);if(line){state.lines.splice(to,0,line);revision++;render();schedulePreview();}}});wrap.append(table);return wrap;
        }
        function lineDetails(row,journal) {
            const backdrop=el('div',{class:'aca-dialog-backdrop'}),dialog=el('div',{class:'aca aca-dialog',role:'dialog','aria-modal':'true','aria-label':'Line details'});
            dialog.append(el('h3',{text:journal?'Journal Item Details':'Invoice Line Details'}));
            if(journal)dialog.append(label('Foreign Amount',input('amount_currency','number',row,drawTotals)),label('Due Date',input('date_maturity','date',row)));
            else dialog.append(label('Description',input('name','text',row)),label('Unit of Measure',picker('uom',{id:row.product_uom_id,name:row.uom_name},selected=>{row.product_uom_id=selected.id;row.uom_name=selected.name;revision++;schedulePreview();})));
            const close=()=>{backdrop.remove();render();schedulePreview();};
            dialog.append(button('Close',close));dialog.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
            backdrop.append(dialog);document.body.append(backdrop);
        }
        function journalItemsTable() {
            const table=el('table',{class:'aca-table aca-journal-preview'});
            const titles=['Account','Partner','Label','Analytic Distribution','Taxes','Debit','Credit','Tax Grids'];
            table.append(el('thead',{},[el('tr',{},titles.map(text=>el('th',{text})))]));
            const body=el('tbody');
            for(const row of state.journal_items||[]){const tr=el('tr');
                for(const [key,text] of [['account',row.account],['partner',row.partner],['name',row.name],['analytic',analyticText(row)],['tax',(row.tax_names||[]).map(t=>t.name).join(', ')],['debit',money(row.debit)],['credit',money(row.credit)],['grids',(row.grid_names||[]).map(t=>t.name).join(', ')]])
                    tr.append(el('td',{class:['debit','credit'].includes(key)?'aca-money':key==='analytic'?'aca-analytic-cell':'',text:text||''}));
                body.append(tr);
            }
            table.append(body);decorateLineGrid(table,{editor:'journal-preview',editable:false});return el('div',{class:'aca-table-wrap','data-journal-items':'true'},[table]);
        }
        function linksPanel() {
            const box = el('div'), incoming = ['receipts','planned-receipts'].includes(state.kind);
            box.append(multiple(incoming ? 'Customer Invoices to Match' : 'Vendor Bills to Match', incoming ? 'invoice_ids' : 'bill_ids', incoming ? 'invoice' : 'bill'));
            if (!incoming) box.append(multiple('Purchase Orders', 'purchase_order_ids', 'po'));
            if (state.kind === 'payments') {
                for (const allocation of state.allocations) box.append(label('PO allocation · ' + allocation.name, input('amount', 'number', allocation)));
                if (state.payment_method === 'journal_transfer') {
                    box.append(el('h4', {text: 'Destination Journals'}));
                    state.destinations.forEach((row, index) => {
                        box.append(picker('journal', {id: row.journal_id, name: row.name}, selected => {row.journal_id = selected.id;row.name = selected.name;render();}),
                            label('Destination amount', input('amount', 'number', row)));
                        if (state.editable) box.append(button('Remove Destination', () => {state.destinations.splice(index,1);render();}));
                    });
                    if (state.editable) box.append(button('Add Destination', () => {state.destinations.push({journal_id: false, name:'',amount:0});render();}));
                }
                if (['journal_transfer','bank_transfer'].includes(state.payment_method)) {
                    const checkbox = el('input', {type:'checkbox', disabled:!state.editable}); checkbox.checked = state.has_bank_fees;
                    checkbox.addEventListener('change', () => {state.has_bank_fees = checkbox.checked;render();});
                    box.append(label('Include Bank Fees',checkbox));
                    if (state.has_bank_fees) box.append(field('Bank Fee Amount','fee_amount','number'),relation('Fee Account','fee_account_id','account'),relation('Fee Tax','fee_tax_id','tax'),analytic(state,'fee_analytic_distribution'));
                }
            }
            return box;
        }
        function attachments() {
            const box = el('div');
            if (!state.id) {box.append(el('p',{text:'Save the draft to attach supporting documents.'}));return box;}
            const list = el('ul',{class:'aca-file-list'});
            for (const file of state.attachments || []) list.append(el('li',{},[el('a',{text:file.name,href:BASE+'/'+state.kind+'/'+state.id+'/attachment/'+file.id+'?company_id='+state.company_id})]));
            box.append(list);
            if (state.editable) {
                const form=el('form',{method:'post',enctype:'multipart/form-data',action:BASE+'/'+state.kind+'/'+state.id+'/attachments'});
                for (const [name,value] of Object.entries({csrf_token:csrf,company_id:state.company_id,version:state.version}))form.append(el('input',{type:'hidden',name,value}));
                form.append(el('input',{type:'file',name:'file',required:true,'aria-label':'Supporting document'}),el('button',{text:'Upload Attachment',type:'submit'}));box.append(form);
            }
            return box;
        }
        function render() {
            const active=document.activeElement, cell=active?.closest?.('[data-grid-column]'), row=active?.closest?.('[data-grid-row]');
            const focus=cell&&row?[Number(row.dataset.gridRow),Number(cell.dataset.gridColumn),active.selectionStart,active.selectionEnd,active.classList?.contains('aca-line-description')]:null;
            closePicker?.();closePicker=null;
            state.selections ||= {};state.allocations ||= [];state.destinations ||= [];state.lines ||= [];
            root.replaceChildren();
            root.append(el('div',{class:'aca-title'},[el('h2',{text:state.name||'New'}),el('span',{class:'aca-badge',text:state.state+(state.review_required || isPlan()?' · '+String(state.review).replaceAll('_',' '):'')})]));
            root.append(actions());
            if(state.material_request_name)root.append(el('p',{class:'aca-mini',text:'Material Request: '+state.material_request_name}));
            status=el('div',{class:'aca-status',role:'status','aria-live':'polite'});root.append(status);
            if(state.comment)root.append(el('div',{class:'aca-alert',text:state.comment}));
            if(state.warnings)root.append(el('div',{class:'aca-alert',text:state.warnings}));
            const surface=el('section',{class:'aca-surface'});surface.append(headerFields());
            const tabs=el('div',{class:'aca-tabs',role:'tablist'});
            const choices=isMove()?[['lines',state.kind==='journals'?'Journal Items':'Invoice Lines'],...(state.kind==='journals'?[]:[['journal','Journal Items']]),['other','Other Information'],['attachments','Attachments']]:
                [['links','Documents & Allocations'],['other','Notes'],['attachments','Attachments']];
            if(state.id)choices.push(['history','Activity Log']);
            if(!choices.some(c=>c[0]===tab))tab=choices[0][0];
            for(const [key,text] of choices)tabs.append(el('button',{type:'button',role:'tab','aria-selected':key===tab,text,onclick:()=>{tab=key;render();}}));
            surface.append(tabs);const panel=el('div',{role:'tabpanel'});
            if(tab==='lines') {
                panel.append(lineTable());
                if(state.editable){
                    const lineActions=el('div',{class:'aca-line-actions absar-line-add'});
                    lineActions.append(button(isBill()?'Add a product':'Add a line',()=>{state.lines.push(blankLine());revision++;render();const next=gridControl(state.lines.length-1,0);next?.focus();}));
                    if(isBill())for(const [type,text]of [['line_section','Add a section'],['line_note','Add a note']])lineActions.append(button(text,()=>{state.lines.push({display_type:type,name:''});render();}));
                    panel.append(lineActions);
                }
                panel.append(el('div',{class:'aca-totals','data-totals':'true'}));
            } else if(tab==='journal') {
                panel.append(el('p',{class:'aca-mini',text:'Journal items reflect the latest successful calculation.'}));
                panel.append(journalItemsTable());
            } else if(tab==='history') {
                for(const item of state.history||[])panel.append(el('article',{class:'aca-history'},[el('strong',{text:item.author}),el('time',{text:item.date}),el('p',{text:item.body})]));
                if(!state.history?.length)panel.append(el('p',{class:'aca-mini',text:'No activity recorded yet.'}));
            } else if(tab==='links')panel.append(linksPanel());
            else if(tab==='other')panel.append(label(isMove()?'Terms and Conditions':'Notes',input(isMove()?'narration':'description','textarea')));
            else panel.append(attachments());
            surface.append(panel);root.append(surface);drawTotals();
            if(focus){const node=focus[4]?root.querySelector('[data-grid-row="'+focus[0]+'"] .aca-line-description'):gridControl(focus[0],focus[1]);if(node){restoringFocus=true;node.focus();restoringFocus=false;
                if(typeof focus[2]==='number'&&(['text','search'].includes(node.type)||node.tagName==='TEXTAREA'))node.setSelectionRange?.(focus[2],focus[3]);}}

        }
        state.payment_method ||= 'cash';state.receipt_method ||= 'cash';state.transaction_type ||= state.kind==='planned-receipts'?'customer':'supplier';state.priority ||= '1';state.funding_status ||= 'funded';
        for(const row of state.lines||[])if(row.subtotal!==undefined)row._amountKey=lineKey(row);
        const derived=new Set(['version','untaxed','tax','total','journal_items','analytic_names','analytic_labels','selections','history','attachments','warnings','comment','roles','subtotal','price_subtotal','price_total','product_name','account_name','partner_name','uom_name','tax_names','grid_names','default_taxes']);
        function draftSignature(){return JSON.stringify(state,(key,value)=>key.startsWith('_')||derived.has(key)?undefined:value);}
        let savedDraft=draftSignature();
        render();savedDraft=draftSignature();
        installDraftNavigation({isDirty:()=>state.editable&&draftSignature()!==savedDraft,
            save:()=>run('save',{...state,submit:false,post:false}),onError:error=>{if(!status?.className?.includes('error'))say(error.message,true);}});
    }
    function start(){const root=document.getElementById('aca-editor');if(root&&!root.dataset.mounted){root.dataset.mounted='true';mount(root);}}
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
