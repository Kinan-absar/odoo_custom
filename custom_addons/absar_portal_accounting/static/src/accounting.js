(function () {
    'use strict';
    const BASE = '/my/employee/accounting';
    function mount(root) {
        let state = JSON.parse(root.dataset.boot), tab = 'lines', busy = false, revision = 0, previewTimer, overpaymentNotice = '', accountingNotice = '';
        const csrf = root.dataset.csrf;
        const isMove = () => ['bills', 'refunds', 'journals'].includes(state.kind);
        const isPlan = () => ['planned', 'planned-receipts'].includes(state.kind);
        const isBill = () => ['bills', 'refunds'].includes(state.kind);
        const money = n => Number(n || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        const lineKey = row => JSON.stringify([state.currency_id,state.partner_id,row.product_id,row.quantity,row.price_unit,row.discount,row.taxes_id,row.product_uom_id]);
        function drawLineAmounts() {
            for(const node of root.querySelectorAll('[data-line-amount]')) {
                const row=state.lines[Number(node.getAttribute('data-line-amount'))];
                node.textContent=row && row._amountKey===lineKey(row)?money(row.subtotal):'Calculating…';
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
        let status;
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
        function picker(resource, selected, choose, disabled = !state.editable) {
            let requestId = 0, timer;
            const box = el('div', {class: 'aca-picker'});
            const control = el('input', {type: 'text', role: 'combobox', 'aria-label': resource + ' search',
                autocomplete: 'off', 'aria-expanded': 'false', disabled, placeholder: 'Search ' + resource + '…'});
            control.value = selected?.name || '';
            const options = el('div', {class: 'aca-options', role: 'listbox', hidden: true});
            async function load() {
                const seq = ++requestId;
                try {
                    const rows = await api('options', {resource, q: control.value, partner_id: state.partner_id});
                    if (seq !== requestId || !box.isConnected) return;
                    options.replaceChildren(); options.hidden = false; control.setAttribute('aria-expanded', 'true');
                    if (!rows.length) options.append(el('div', {class: 'aca-mini', text: 'No matching records'}));
                    for (const row of rows) options.append(el('button', {type: 'button', role: 'option', text: row.name,
                        onmousedown: event => event.preventDefault(), onclick: () => {
                            control.value = row.name; options.hidden = true; control.setAttribute('aria-expanded', 'false');
                            choose(row); revision++;
                        }}));
                } catch (error) {say(error.message, true);}
            }
            control.addEventListener('focus', () => {control.value = ''; load();});
            control.addEventListener('input', () => {clearTimeout(timer); timer = setTimeout(load, 180);});
            control.addEventListener('blur', () => {options.hidden = true; control.setAttribute('aria-expanded', 'false'); control.value = selected?.name || '';});
            control.addEventListener('keydown', event => {
                if (event.key === 'Escape') {options.hidden = true; control.blur();}
                if (event.key === 'ArrowDown') {event.preventDefault(); options.querySelector('button')?.focus();}
            });
            box.append(control, options);
            if (!disabled && selected?.id) box.append(button('Clear', () => {choose({id: false, name: ''}); revision++; render();}));
            return box;
        }
        function relation(title, name, resource, onPick) {
            return label(title, picker(resource, state.selections[name], row => {
                state[name] = row.id; state.selections[name] = row;
                if(name==='currency_id')state.currency_name=row.name;
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
        function analytic(target, key = 'analytic_distribution') {
            const control = button(Object.keys(target[key] || {}).length ? 'Edit distribution' : 'Set distribution', () => {
                const original = target[key] || {};
                let rows = Object.entries(original).map(([id, percent]) => ({id, percent, name: 'Analytic ' + id}));
                const backdrop = el('div', {class: 'aca-dialog-backdrop'}), dialog = el('div', {class: 'aca aca-dialog', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Analytic distribution'});
                function draw() {
                    dialog.replaceChildren(el('h3', {text: 'Analytic distribution'}));
                    for (const row of rows) {
                        const grid = el('div', {class: 'aca-grid'});
                        grid.append(picker('analytic', {id: row.id, name: row.name}, selected => {row.id = String(selected.id); row.name = selected.name; draw();}, !state.editable));
                        const percent = el('input', {type: 'number', min: 0, max: 100, step: 'any', 'aria-label': 'Percentage', disabled: !state.editable});
                        percent.value = row.percent;
                        percent.addEventListener('input', () => row.percent = Number(percent.value));
                        grid.append(label('Percentage', percent));
                        if (state.editable) grid.append(button('Remove', () => {rows = rows.filter(r => r !== row); draw();}));
                        dialog.append(grid);
                    }
                    if (state.editable) dialog.append(button('Add analytic account', () => {rows.push({id: '', name: '', percent: 100}); draw();}));
                    dialog.append(button('Close', () => backdrop.remove()));
                    if (state.editable) dialog.append(button('Apply', () => {
                        const distribution = {};
                        for (const row of rows) {
                            if (!row.id || !Number.isFinite(row.percent) || row.percent < 0 || row.percent > 100) {say('Choose analytic accounts and percentages between 0 and 100.', true); return;}
                            distribution[row.id] = row.percent;
                        }
                        target[key] = distribution; revision++; backdrop.remove(); render();
                    }, true));
                }
                backdrop.append(dialog); document.body.append(backdrop); draw();
            });
            return control;
        }
        function schedulePreview() {
            clearTimeout(previewTimer);
            previewTimer = setTimeout(preview, 650);
        }
        async function preview() {
            if (!state.editable || !isMove() || busy) return;
            const seq = revision;
            const totals = root.querySelector('[data-totals]');
            if (totals) totals.dataset.pending = 'true';
            try {
                const result = await api('preview', state);
                if (seq !== revision) return;
                state.untaxed = result.untaxed; state.tax = result.tax; state.total = result.total;
                state.currency_name=result.currency;
                (result.line_amounts||[]).forEach((value,index)=>{if(state.lines[index]){state.lines[index].subtotal=value;state.lines[index]._amountKey=lineKey(state.lines[index]);}});
                drawLineAmounts();drawTotals(); say('Totals updated.');
            } catch (error) {if (seq === revision) say('Totals pending: ' + error.message, true);}
        }
        function drawTotals() {
            const node = root.querySelector('[data-totals]'); if (!node) return;
            node.replaceChildren(); node.dataset.pending = 'false';
            if (state.kind === 'journals') {
                const debit = state.lines.reduce((n, l) => n + Number(l.debit || 0), 0);
                const credit = state.lines.reduce((n, l) => n + Number(l.credit || 0), 0);
                for (const [title, value] of [['Debit', debit], ['Credit', credit], ['Difference', debit - credit]]) node.append(el('div', {}, [el('span', {text: title}), el('strong', {text: money(value)})]));
            } else {
                for (const [title, value] of [['Untaxed Amount', state.untaxed], ['Taxes', state.tax], ['Total', state.total]]) node.append(el('div', {}, [el('span', {text: title}), el('strong', {text: money(value) + ' ' + (state.currency_name || state.currency || '')})]));
            }
        }
        async function run(operation, payload) {
            if (busy) return;
            busy = true; clearTimeout(previewTimer); root.querySelectorAll('button').forEach(b => b.disabled = true); say('Working…');
            try {
                const result = await api(operation, payload);
                if (result.redirect) {window.location.assign(result.redirect); return;}
                state = result; revision++;
                for(const row of state.lines||[])if(row.subtotal!==undefined)row._amountKey=lineKey(row);
                if (state.id) history.replaceState(null, '', BASE + '/' + state.kind + '/' + state.id + '?company_id=' + state.company_id);
                busy = false; render(); say('Saved successfully.');
            } catch (error) {
                busy = false;
                if(error.message.startsWith('PO OVERPAYMENT:'))overpaymentNotice=error.message;
                if(error.message.startsWith('ACCOUNTING WARNING:'))accountingNotice=error.message;
                render(); say(error.message, true);
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
            const box = el('div', {class: 'aca-actions'});
            if (state.editable) {
                box.append(button('Save Draft', () => run('save', {...state, submit: false, post:false}), true));
                if (state.can_post && !isPlan()) box.append(button('Post',()=>reviewDialog(),true));
                else if (state.kind !== 'planned-receipts' && (isPlan() || state.review_required !== false)) box.append(button(isPlan() ? 'Submit to CEO' : 'Submit for Approval', () => run('save', {...state, submit: true, post:false})));
                if (state.id && !isPlan()) box.append(button('Cancel Draft', () => {
                    if (window.confirm('Cancel this draft document?')) action('cancel');
                }));
            }
            if (state.can_review && !isPlan()) box.append(button('Approve & Post', () => reviewDialog(), true), button('Return for Correction', () => reviewDialog(true)));
            if (state.id && ['payments', 'receipts'].includes(state.kind)) {
                if (state.editable) box.append(button('Find Matching ' + (state.kind === 'payments' ? 'Bills' : 'Invoices'), () => action('find')));
                if (state.state === 'posted' && (state.roles.approver || state.roles.direct)) box.append(button('Reconcile', () => action('reconcile')), button('Unreconcile', () => {
                    if (window.confirm('Remove only the reconciliations managed by this voucher?')) action('unreconcile');
                }));
            }
            if (state.id && ['bills', 'refunds', 'journals', 'payments', 'receipts'].includes(state.kind)) box.append(el('a', {text: 'Print PDF', class: 'aca-primary', target: '_blank', rel: 'noopener', href: BASE + '/' + state.kind + '/' + state.id + '/print?company_id=' + state.company_id}));
            if(state.id && (isMove() || (['payments','receipts'].includes(state.kind) && state.state==='posted'))) box.append(el('a',{text:'Print Journal Entry',class:'aca-print-link',target:'_blank',rel:'noopener',href:BASE+'/'+state.kind+'/'+state.id+'/print?company_id='+state.company_id+'&journal_entry=1'}));
            if (state.id && state.kind === 'bills' && state.state === 'posted' && state.roles.preparer && state.balance_due > 0) box.append(el('a', {text:'Create Payment Voucher',class:'aca-primary',href:BASE+'/payments/new?company_id='+state.company_id+'&bill_id='+state.id}));
            if (state.id && !isPlan() && (state.roles.preparer || state.roles.approver) && ['posted','cancel'].includes(state.state)) {
                if (state.portal_accounting_reset_pending) box.append(el('span',{class:'aca-mini',text:'Reset permission requested — awaiting internal review'}));
                else box.append(button('Request Reset to Draft', () => {
                    const comment=window.prompt('Why is a reset needed? The document stays posted until an authorized internal user completes the existing reset approval.');
                    if(comment?.trim())action('request-reset',{comment});
                }));
            }
            if (isPlan() && state.id) {
                if(state.roles.preparer&&!state.editable&&state.state!=='executed'){
                    if(state.reset_request_pending)box.append(el('span',{class:'aca-mini',text:'Reset approval pending'}));
                    else box.append(button('Request Reset to Draft',()=>{
                        if(window.confirm('Request approval from an existing Payment Execution Manager to reset this movement?'))action('request-reset');
                    }));
                }
                if (state.roles.preparer && (state.state === 'executed' || state.kind === 'planned-receipts')) box.append(button('Create Voucher', () => action('create-voucher')));
                if (state.is_ceo && !state.run_id) box.append(button('Add to Weekly Plan', () => planDialog()));
                if (state.is_ceo && state.kind === 'planned' && ['pending', 'held'].includes(state.review)) {
                    box.append(button('Approve Payment', () => planDialog(true), true));
                    for (const [name, title] of [['hold', 'Hold'], ['reject', 'Reject']]) box.append(button(title, () => {
                        const comment = window.prompt('CEO comment'); if (comment !== null) action(name, {comment});
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
                grid.append(relation('Vendor', 'partner_id', 'partner'), field('Bill Reference', 'ref'), field('Bill Date', 'invoice_date', 'date'),
                    field('Accounting Date', 'date', 'date'), relation('Journal', 'journal_id', 'journal'), relation('Currency', 'currency_id', 'currency'),
                    relation('Payment Terms', 'invoice_payment_term_id', 'term'), field('Due Date', 'invoice_date_due', 'date'),
                    field('Payment Reference', 'payment_reference'), relation('Recipient Bank', 'partner_bank_id', 'bank'));
                if (state.editable) grid.append(label('Auto-complete from Purchase Order', picker('po', null, async row => {
                    try {
                        const result = await api('po-lines', {po_id: row.id});
                        if (state.lines.length && !window.confirm('Replace the current bill lines with this PO’s billable lines?')) return;
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
        function lineTable() {
            const journal = state.kind === 'journals', wrap = el('div', {class: 'aca-table-wrap'}), table = el('table', {class: 'aca-table aca-lines'});
            const titles = journal ? ['Label', 'Account', 'Partner', 'Debit', 'Credit', 'Actions'] :
                ['Product / Description', 'Quantity', 'UoM', 'Unit Price', 'Discount %', 'Taxes', 'Amount', 'Actions'];
            table.append(el('thead', {}, [el('tr', {}, titles.map(text => el('th', {text})))]));
            const body = el('tbody');
            state.lines.forEach((row, index) => {
                const tr = el('tr', {class:'aca-line-row'}), details = el('div', {class:'aca-line-details'}), td = (child, className = '') => {const cell = el('td', {class: className}, [child]); tr.append(cell); return cell;};
                if (['line_section','line_note'].includes(row.display_type)) {
                    const cell = td(input('name', 'text', row)); cell.colSpan = titles.length - 1;
                } else {
                    const desc = el('div');
                    if (!journal) desc.append(picker('product', {id: row.product_id, name: row.product_name}, selected => {
                        row.product_id = selected.id; row.product_name = selected.name; row.name = selected.name;
                        row.account_id = selected.account_id; row.account_name = selected.account_name;
                        row.product_uom_id = selected.product_uom_id; row.uom_name = selected.uom_name;
                        row.taxes_id = (selected.tax_ids || []).map(t => t.id); row.tax_names = selected.tax_ids || [];
                        render(); schedulePreview();
                    }));
                    desc.append(input('name', 'text', row)); td(desc, 'desc');
                    const account = picker('account', {id: row.account_id, name: row.account_name}, selected => {
                        row.account_id = selected.id; row.account_name = selected.name; render(); schedulePreview();
                    });
                    if (journal) td(account, 'account');
                    else details.append(label('Expense Account', account));
                    if (journal) {
                        td(picker('partner', {id: row.partner_id, name: row.partner_name}, selected => {row.partner_id = selected.id; row.partner_name = selected.name; render();}));
                        for (const key of ['debit','credit']) td(input(key, 'number', row, drawTotals));
                        details.append(label('Foreign Amount',input('amount_currency','number',row,drawTotals)), label('Due Date',input('date_maturity','date',row)));
                        const grids=el('div');
                        grids.append(picker('tax-grid', null, selected=>{
                            row.tax_tag_ids ||= [];row.grid_names ||= [];
                            if(!row.tax_tag_ids.includes(selected.id)){row.tax_tag_ids.push(selected.id);row.grid_names.push(selected);}
                            render();
                        }));
                        for(const grid of row.grid_names||[]){
                            const pill=el('span',{class:'aca-pill',text:grid.name});
                            if(state.editable)pill.append(button('×',()=>{row.tax_tag_ids=row.tax_tag_ids.filter(id=>id!==grid.id);row.grid_names=row.grid_names.filter(g=>g.id!==grid.id);render();}));
                            grids.append(pill);
                        }
                        details.append(label('Tax Grids', grids));
                    } else {
                        td(input('quantity', 'number', row));
                        td(picker('uom', {id: row.product_uom_id, name: row.uom_name}, selected => {row.product_uom_id=selected.id;row.uom_name=selected.name;render();schedulePreview();}));
                        for (const key of ['price_unit','discount']) td(input(key, 'number', row));
                        const taxes = el('div');
                        taxes.append(picker('tax', null, selected => {
                            row.taxes_id ||= []; row.tax_names ||= [];
                            if (!row.taxes_id.includes(selected.id)) {row.taxes_id.push(selected.id); row.tax_names.push(selected);}
                            render(); schedulePreview();
                        }));
                        for (const tax of row.tax_names || []) {
                            const tag = el('span', {class: 'aca-pill', text: tax.name});
                            if (state.editable) tag.append(button('×', () => {row.taxes_id = row.taxes_id.filter(id => id !== tax.id); row.tax_names = row.tax_names.filter(t => t.id !== tax.id); render(); schedulePreview();}));
                            taxes.append(tag);
                        }
                        td(taxes);
                    }
                    details.append(label('Analytic Distribution', analytic(row)));
                    if (!journal) td(el('span', {'data-line-amount':index,text:row._amountKey===lineKey(row)?money(row.subtotal):'Calculating…'}), 'aca-money');
                }
                const controls = el('div', {class:'aca-row-actions'});
                if (state.editable) {
                    controls.append(button('↑', () => {if(index) [state.lines[index-1],state.lines[index]]=[state.lines[index],state.lines[index-1]];revision++;render();}),
                        button('↓', () => {if(index < state.lines.length-1) [state.lines[index+1],state.lines[index]]=[state.lines[index],state.lines[index+1]];revision++;render();}),
                        button('Remove', () => {state.lines.splice(index,1);revision++;render();schedulePreview();}));
                }
                for (const control of controls.children) {
                    control.setAttribute('aria-label', (control.textContent === '↑' ? 'Move line up' : control.textContent === '↓' ? 'Move line down' : 'Remove line') + ' ' + (index+1));
                    control.setAttribute('title', control.getAttribute('aria-label'));
                }
                td(controls); body.append(tr);
                if (details.children.length) {
                    const cell=el('td', {colspan:titles.length}, [details]);
                    body.append(el('tr', {class:'aca-line-detail-row'}, [cell]));
                }
            });
            table.append(body); wrap.append(table); return wrap;
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
            state.selections ||= {};state.allocations ||= [];state.destinations ||= [];state.lines ||= [];
            root.replaceChildren();
            root.append(el('div',{class:'aca-title'},[el('h2',{text:state.name||'New'}),el('span',{class:'aca-badge',text:state.state+(state.review_required || isPlan()?' · '+String(state.review).replaceAll('_',' '):'')})]));
            root.append(actions());status=el('div',{class:'aca-status',role:'status','aria-live':'polite'});root.append(status);
            if(state.comment)root.append(el('div',{class:'aca-alert',text:state.comment}));
            if(state.warnings)root.append(el('div',{class:'aca-alert',text:state.warnings}));
            const surface=el('section',{class:'aca-surface'});surface.append(headerFields());
            const tabs=el('div',{class:'aca-tabs',role:'tablist'});
            const choices=isMove()?[['lines',state.kind==='journals'?'Journal Items':'Invoice Lines'],['journal','Journal Preview'],['other','Other Information'],['attachments','Attachments']]:
                [['links','Documents & Allocations'],['other','Notes'],['attachments','Attachments']];
            if(state.id)choices.push(['history','Activity Log']);
            if(!choices.some(c=>c[0]===tab))tab=choices[0][0];
            for(const [key,text] of choices)tabs.append(el('button',{type:'button',role:'tab','aria-selected':key===tab,text,onclick:()=>{tab=key;render();}}));
            surface.append(tabs);const panel=el('div',{role:'tabpanel'});
            if(tab==='lines') {
                panel.append(lineTable());
                if(state.editable){
                    panel.append(button('Add a Line',()=>{state.lines.push({name:'',quantity:1,price_unit:0,discount:0,debit:0,credit:0,taxes_id:[],tax_names:[],analytic_distribution:{}});render();}));
                    if(isBill())for(const [type,text]of [['line_section','Add a Section'],['line_note','Add a Note']])panel.append(button(text,()=>{state.lines.push({display_type:type,name:''});render();}));
                    panel.append(button('Recalculate Totals',preview));
                }
                panel.append(el('div',{class:'aca-totals','data-totals':'true'}));
            } else if(tab==='journal') {
                panel.append(el('p',{class:'aca-mini',text:'Journal items from the last saved draft. Save after editing to refresh them.'}));
                const table=el('table',{class:'aca-table'});table.append(el('thead',{},[el('tr',{},['Account','Partner','Label','Debit','Credit'].map(text=>el('th',{text})))]));
                const body=el('tbody');for(const row of state.journal_items||[])body.append(el('tr',{},['account','partner','name','debit','credit'].map(k=>el('td',{text:['debit','credit'].includes(k)?money(row[k]):row[k]||''}))));table.append(body);panel.append(el('div',{class:'aca-table-wrap'},[table]));
            } else if(tab==='history') {
                for(const item of state.history||[])panel.append(el('article',{class:'aca-history'},[el('strong',{text:item.author}),el('time',{text:item.date}),el('p',{text:item.body})]));
                if(!state.history?.length)panel.append(el('p',{class:'aca-mini',text:'No activity recorded yet.'}));
            } else if(tab==='links')panel.append(linksPanel());
            else if(tab==='other')panel.append(label(isMove()?'Terms and Conditions':'Notes',input(isMove()?'narration':'description','textarea')));
            else panel.append(attachments());
            surface.append(panel);root.append(surface);drawTotals();
        }
        state.payment_method ||= 'cash';state.receipt_method ||= 'cash';state.transaction_type ||= state.kind==='planned-receipts'?'customer':'supplier';state.priority ||= '1';state.funding_status ||= 'funded';
        for(const row of state.lines||[])if(row.subtotal!==undefined)row._amountKey=lineKey(row);
        render();
    }
    function start(){const root=document.getElementById('aca-editor');if(root&&!root.dataset.mounted){root.dataset.mounted='true';mount(root);}}
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
