/** @odoo-module **/
import { installDraftNavigation } from "./draft_navigation";
import { calculationRows, isEmptyDraftLine, decorateLineGrid } from "./line_grid";
import { createPurchaseUI } from "./purchase_ui";
import { openPurchaseProductDialog } from "./purchase_product_form";
import { openPurchaseReceiptDialog } from "./purchase_receipt";
// No backend webclient RPC or generic model access is exposed to portal users.
function startPurchaseWorkspace() {
    const root = document.getElementById('apw-root');
    if (!root || root.dataset.ready) return;
    root.dataset.ready = '1';
    const boot = JSON.parse(document.getElementById('apw-boot').textContent);
    const state = structuredClone(boot.values);
    const readonly = boot.readonly;
    const labels = structuredClone(boot.selected);
    const csrf = document.getElementById('apw-csrf').value;
    let dirty = false, busy = false, previewSequence = 0, pendingComputations = 0;
    const defaultJobs=new Set();
    function trackDefaults(job){defaultJobs.add(job);job.then(()=>defaultJobs.delete(job),()=>defaultJobs.delete(job));return job;}
    function vendorDefaults(...args){return trackDefaults(loadVendorDefaults(...args));}
    function reprice(...args){return trackDefaults(loadLinePrice(...args));}
    function defaultsFor(...args){return trackDefaults(loadProductDefaults(...args));}
    let totals = boot.totals || null;
    let totalsPending = false;
    const errorBox = document.getElementById('apw-error');
    const status = document.getElementById('apw-status');
    let previewTimer;
    const byId = id => document.getElementById(id);
    const text = (tag, value, className = '') => {
        const node = document.createElement(tag);
        node.textContent = value ?? '';
        if (className) node.className = className;
        return node;
    };
    const money = value => Number(value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const amountKey = line => JSON.stringify([line.product_qty, line.price_unit, line.discount || 0,
        line.taxes_id, line.product_uom, state.currency_id, state.company_id]);
    const lineAmount = line => line && Number.isFinite(Number(line.price_subtotal)) ? Number(line.price_subtotal) : null;
    state.lines.forEach(line => {line._amountKey = amountKey(line);});
    const changed = () => {
        dirty = true; previewSequence++; totalsPending = true; renderTotals();
        root.querySelectorAll('[data-line-amount]').forEach(node => {
            const line = state.lines[Number(node.dataset.lineAmount)];
            if (line) node.textContent = lineAmount(line) === null ? '—' : money(lineAmount(line));
        });
        clearTimeout(previewTimer);
        previewTimer = setTimeout(() => {if(!busy&&!pendingComputations)recalculate().catch(showError);}, 250);
    };
    const showError = error => {totalsPending=false;renderTotals();errorBox.textContent = error.message || String(error); errorBox.hidden = false; errorBox.scrollIntoView({block: 'nearest'});};
    const clearError = () => {errorBox.hidden = true; errorBox.textContent = '';};
    async function post(path, payload) {
        const response = await fetch('/my/employee/purchase' + path, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            body: new URLSearchParams({csrf_token: csrf, payload: JSON.stringify(payload)})
        });
        const type = response.headers.get('content-type') || '';
        if (!type.includes('application/json')) throw new Error(response.status === 401 || response.status === 403 ?
            'Your session or purchase permission has changed. Reload this page.' :
            'The server returned an unexpected response (HTTP ' + response.status + '). Ask your administrator to check the server log.');
        const result = await response.json();
        if (!response.ok || result.error) throw new Error(result.error || 'The request could not be completed.');
        return result;
    }
    function payload() {return {...state, lines:calculationRows(state.lines), id: boot.id, version: boot.version};}
    function field(label, input, host, hint = '') {
        const wrap = document.createElement('div');
        const labelNode = text('label', label);
        if (input.id) labelNode.htmlFor = input.id;
        wrap.append(labelNode, input);
        if (hint) wrap.append(text('small', hint, 'apw-help'));
        host.append(wrap);
        return input;
    }
    function input(value, type, onChange) {
        const node = document.createElement('input');
        node.type = type || 'text';
        node.value = value ?? '';
        node.className = 'form-control';
        node.disabled = readonly;
        if (type === 'number') node.step = 'any';
        if (type === 'datetime-local') node.step = '1';
        let lastValue = node.value;
        const commit = () => {
            if (node.value === lastValue) return;
            lastValue = node.value;
            onChange(node.value); changed();
        };
        node.addEventListener('input', commit);
        node.addEventListener('change', commit);
        return node;
    }
    function button(label, callback, cls = 'btn btn-light') {
        const node = text('button', label, cls);
        node.type = 'button';
        node.addEventListener('click', callback);
        return node;
    }
    function lookup(kind, selected, onSelect, extras = {}, actions = {}) {
        const ui = createPurchaseUI({root, post, companyId: state.company_id, readonly});
        return ui.lookup(kind, selected, async item => {await onSelect(item); if (!readonly) changed();}, extras,
            {...actions, onError: showError});
    }
    async function productForm(productId, initialName, onSaved) {
        const ui = createPurchaseUI({root, post, companyId: state.company_id});
        await openPurchaseProductDialog({...ui, post, companyId: state.company_id,
            productId, initialName, saveLabel: productId ? 'Save Product' : 'Create and Add',
            onCreate: async item => {await onSaved(item);}});
    }
    function headerChoice(host, label, name, kind, hint) {
        field(label, lookup(kind, labels[name], item => {
            state[name] = item?.id || 0; labels[name] = item;
            if(name==='partner_id')vendorSequence++;
            if (name === 'partner_id' && item) vendorDefaults().catch(showError);
            else if (['currency_id', 'fiscal_position_id'].includes(name)) repriceAll();
            if (name === 'project_id') {state.material_request_id = 0; labels.material_request_id = null; renderHeader();}
            if (name === 'material_request_id' && item) linkMaterial(item.id).catch(showError);
        }), host, hint);
    }
    function renderHeader() {
        const header = byId('apw-header'), other = byId('apw-other');
        [header, other].forEach(host => host.querySelectorAll('.apw-lookup').forEach(node => node.dispatchEvent(new Event('apw-dispose'))));
        header.replaceChildren(); other.replaceChildren();
        headerChoice(header, 'Vendor *', 'partner_id', 'vendor');
        field(['purchase', 'done'].includes(boot.state) ? 'Order Date' : 'Order Deadline *', input(state.date_order, 'datetime-local', v => {state.date_order = v;}), header);
        field('Vendor Reference', input(state.partner_ref, 'text', v => {state.partner_ref = v;}), header);
        field('Expected Arrival', input(state.date_planned, 'datetime-local', v => {
            state.date_planned = v;
            for (const line of state.lines) if (!line.display_type) line.date_planned = v;
            renderLines();
        }), header, 'Sets the arrival date on all product lines. Individual dates remain editable below.');
        headerChoice(header, 'Material Request', 'material_request_id', 'mr', 'All approved requests requiring a PO in this company.');
        if (!readonly && state.material_request_id) {
            header.append(button('Import Material Request lines', () => importMaterial().catch(showError), 'btn btn-outline-secondary'));
        }
        headerChoice(header, 'Project', 'project_id', 'project', 'All active projects available to this company.');
        headerChoice(header, 'Currency *', 'currency_id', 'currency');
        const buyer = text('input', ''); buyer.className = 'form-control';
        buyer.value = labels.user_id?.label || ''; buyer.readOnly = true;
        field('Buyer', buyer, other, 'The employee who prepared this request.');
        const company = document.createElement('select'); company.className = 'form-select';
        company.disabled = readonly || Boolean(boot.id);
        for (const c of boot.companies) {const o = text('option', c.label); o.value = c.id; company.append(o);}
        company.value = state.company_id;
        company.addEventListener('change', async () => {
            if (dirty && !await ask('Changing company clears vendor, project, accounting selections and lines. Continue?')) {company.value = state.company_id; return;}
            vendorSequence++;
            totals = null; totalsPending = false;
            state.company_id = Number(company.value); state.lines = []; state.material_request_id = 0;
            for (const k of Object.keys(labels)) {if (k !== 'user_id') {labels[k] = null; state[k] = 0;}}
            const selectedCompany = boot.companies.find(c => c.id === state.company_id);
            labels.currency_id = selectedCompany?.currency || null; state.currency_id = labels.currency_id?.id || 0;
            labels.picking_type_id = selectedCompany?.picking_type || null; state.picking_type_id = labels.picking_type_id?.id || 0;
            changed(); renderHeader(); renderLines();
        });
        field('Company', company, other);
        field('Source Document', input(state.origin, 'text', v => {state.origin = v;}), other);
        headerChoice(other, 'Deliver To', 'picking_type_id', 'picking_type');
        headerChoice(other, 'Payment Terms', 'payment_term_id', 'payment_term');
        headerChoice(other, 'Fiscal Position', 'fiscal_position_id', 'fiscal_position');
        headerChoice(other, 'Incoterm', 'incoterm_id', 'incoterm');
        field('Incoterm Location', input(state.incoterm_location, 'text', v => {state.incoterm_location = v;}), other);
    }
    async function linkMaterial(id) {
        const info = await post('/mr-info', {company_id: state.company_id, mr_id: id});
        if (state.material_request_id !== id) return;
        state.project_id = info.project.id; labels.project_id = info.project;
        if (!state.origin) state.origin = info.name;
        changed(); renderHeader();
    }
    async function importMaterial() {
        if (!state.material_request_id) throw new Error('Choose a Material Request first.');
        if (state.lines.length && !await ask('Replace current draft lines with the selected Material Request materials?')) return;
        const info = await post('/mr-info', {company_id: state.company_id, mr_id: state.material_request_id});
        state.project_id = info.project.id; labels.project_id = info.project;
        state.lines = info.lines; changed(); renderHeader(); renderLines();
        repriceAll();
    }
    let vendorSequence = 0;
    async function loadVendorDefaults() {
        const seq = ++vendorSequence;
        pendingComputations++;
        try {
            const result = await post('/vendor-defaults', {partner_id: state.partner_id, company_id: state.company_id});
            if (seq !== vendorSequence) return;
            for (const [name, item] of Object.entries(result.selected)) {labels[name] = item; state[name] = item?.id || 0;}
            if (!state.notes) {state.notes = result.notes; byId('apw-notes').value = state.notes;}
            renderHeader(); changed(); repriceAll();
        } finally {pendingComputations--; if (!pendingComputations) changed();}
    }
    async function loadLinePrice(line, force=false) {
        if (!line.product_id) return;
        const seq = (line._priceSequence || 0) + 1; line._priceSequence = seq;
        const vendorVersion=vendorSequence, productId=line.product_id, selection=line._sequence;
        pendingComputations++;
        try {
            const result = await post('/preview', {...payload(), defaults: true, lines: [line]});
            if (line._priceSequence !== seq || vendorVersion!==vendorSequence || line.product_id!==productId || line._sequence!==selection || !state.lines.includes(line)) return;
            const native = result.lines[0];
            if (!line.product_uom) {line.product_uom = native.product_uom; line.uom_label = native.uom_label;}
            if (!line.name) line.name = native.name;
            if (!line.date_planned) line.date_planned = native.date_planned;
            if (!line._manualPrice) {line.price_unit = native.price_unit; line.discount = native.discount;}
            if(force||!line._manualTaxes){line.taxes_id = native.taxes_id; line.taxes = native.taxes;}
            line.default_account = native.default_account;
            changed(); renderLines();
        } catch (error) {showError(error);}
        finally {pendingComputations--; if (!pendingComputations) changed();}
    }
    function repriceAll() {
        for (const line of state.lines) if (!line.display_type) reprice(line,true);
    }
    function blankLine(display = '') {
        const taxes=display?[]:(boot.companies.find(c=>c.id===state.company_id)?.default_taxes||boot.default_taxes||[]);
        return {id: 0, display_type: display, product_id: 0, product_label: '', name: '',
            product_qty: 1, product_uom: 0, price_unit: 0, discount: 0, taxes_id: taxes.map(t=>t.id), taxes: taxes.map(t=>({...t})), _defaultTaxes: taxes.map(t=>t.id),
            analytic_distribution: {}, analytic_labels: {}, date_planned: state.date_planned || '',
            absar_expense_account_id: 0, account_label: '', default_account: ''};
    }
    async function selectLineProduct(line, item) {
        if (readonly) return;
        if (item?.product_updated && item.id === line.product_id) {
            // Catalog/account changes must not reprice a negotiated PO line.
            for (const row of state.lines.filter(row => row.product_id === item.id)) {
                row.product_label = item.label; row.default_account = item.default_account || '';
                row.absar_expense_account_id = 0; row.account_label = '';
            }
            changed(); renderLines(); return;
        }
        return defaultsFor(line, item);
    }
    async function loadProductDefaults(line, product) {
        if (!product) {line.product_id = 0; line.product_label = ''; return;}
        line.absar_expense_account_id = 0; line.account_label = '';
        const sequence = (line._sequence || 0) + 1; line._sequence = sequence;
        const vendorVersion=vendorSequence;
        pendingComputations++;
        line.product_id = product.id; line.product_label = product.label;
        line._manualPrice = false; line._manualTaxes=false;
        line.product_uom = 0;
        try {
            const response = await post('/preview', {...payload(), defaults: true, lines: [line]});
            if (line._sequence !== sequence || vendorVersion!==vendorSequence || !state.lines.includes(line)) return;
            const ident = line.id;
            const manualPrice = line._manualPrice ? {price_unit: line.price_unit, discount: line.discount, price_subtotal:line.price_subtotal, price_total:line.price_total, _manualPrice: true} : {_manualPrice: false};
            const manualTaxes=line._manualTaxes?{taxes_id:line.taxes_id,taxes:line.taxes}:{};
            Object.assign(line, response.lines[0], {id: ident, _sequence: sequence}, manualPrice,manualTaxes);
            if (state.date_planned) line.date_planned = state.date_planned;
            changed(); renderLines();
        } catch (error) {showError(error);}
        finally {pendingComputations--; if (!pendingComputations) changed();}
    }
    function renderLines() {
        const host = byId('apw-lines');
        const active = document.activeElement, activeRow = active?.closest('[data-grid-row]');
        const focus = activeRow && host.contains(active) ? {
            row: Number(activeRow.dataset.gridRow), column: Number(active.closest('td').dataset.gridColumn),
            description: active.classList.contains('apw-description'), start: active.selectionStart, end: active.selectionEnd,
            query: active.getAttribute('role') === 'combobox' && !state.lines[Number(activeRow.dataset.gridRow)]?.product_id ? active.value : null
        } : null;
        host.querySelectorAll('.apw-lookup').forEach(node => node.dispatchEvent(new Event('apw-dispose')));
        host.replaceChildren();
        if (!state.lines.length) {const row = document.createElement('tr'), cell = text('td', 'Add a product, section or note.', 'apw-empty'); cell.colSpan = 9; row.append(cell); host.append(row);}
        state.lines.forEach((line, index) => {
            const row = document.createElement('tr'); row.dataset.gridRow = String(index);
            function cell(node, className = '') {
                const td = document.createElement('td'); td.className = className; td.dataset.gridColumn = String(row.children.length);
                td.append(node); row.append(td);
                const entry = node.matches?.('input, textarea, button') ? node : (node.querySelector('input') || node.querySelector('button'));
                if (entry && row.children.length <= 7 && !node.classList?.contains('apw-row-actions')) {entry.dataset.gridEntry = '1'; entry.setAttribute('aria-label', entry.getAttribute('aria-label') || ['Product', 'Analytic distribution', 'Quantity', 'Unit', 'Unit price', 'Taxes', 'Discount'][row.children.length-1]);}
                return td;
            }
            if (line.display_type) {
                const label = input(line.name, 'text', v => {line.name = v;});
                const td = cell(label, line.display_type === 'line_section' ? 'apw-section' : 'apw-note'); td.colSpan = 8;
            } else {
                if (!line.product_id) row.classList.add('apw-products-missing');
                const productCell = document.createElement('div');
                if (!line.product_id && line.name) productCell.append(text('small', 'Select a product for this material', 'apw-help'));
                productCell.append(lookup('product', {id: line.product_id, label: line.product_label},
                    item => selectLineProduct(line, item), {}, {productForm, advance: () => moveGrid(index, 0, 1)}));
                const description = document.createElement('textarea'); description.className = 'form-control apw-description'; description.rows = 1;
                description.value = line.name; description.disabled = readonly; description.setAttribute('aria-label', 'Line description');
                description.addEventListener('input', () => {line.name = description.value; changed();});
                productCell.append(description); cell(productCell);
                const analytic = document.createElement('div');
                const descriptionText = Object.entries(line.analytic_distribution || {}).map(([key, pct]) =>
                    key.split(',').map(id => line.analytic_labels?.[id]?.label || id).join(' + ') + ': ' + pct + '%').join('; ');
                analytic.append(button(descriptionText || (readonly ? '—' : 'Set distribution'), () => analyticDialog(line), 'btn btn-link apw-analytic'));
                cell(analytic);
                const quantity=input(line.product_qty, 'number', v => {line.product_qty = Number(v);});quantity.addEventListener('change',()=>reprice(line));cell(quantity, 'num');
                cell(lookup('uom', {id: line.product_uom, label: line.uom_label}, item => {
                    line.product_uom = item?.id || 0; line.uom_label = item?.label || ''; if (item) reprice(line);
                }, {product_id: line.product_id}, {advance: () => moveGrid(index, 3, 1)}));
                cell(input(line.price_unit, 'number', v => {line.price_unit = Number(v); line._manualPrice = true;}), 'num');
                const tax = document.createElement('div');
                for (const selected of line.taxes || []) {
                    const chip = text('span', selected.label, 'apw-chip');
                    if (!readonly) chip.append(button('×', () => {line._manualTaxes=true;line.taxes_id = line.taxes_id.filter(id => id !== selected.id); line.taxes = line.taxes.filter(t => t.id !== selected.id); changed(); renderLines();}, 'apw-chip-remove'));
                    tax.append(chip);
                }
                if (!readonly) tax.append(lookup('tax', null, item => {
                    if (item && !line.taxes_id.includes(item.id)) {line._manualTaxes=true;line.taxes_id.push(item.id); line.taxes.push(item); changed(); renderLines();}
                }, {}, {advance: () => moveGrid(index, 5, 1)}));
                cell(tax, 'apw-tax-cell');
                cell(input(line.discount || 0, 'number', v => {line.discount = Number(v);}), 'num');
                const amount = text('span', lineAmount(line) === null ? '—' : money(lineAmount(line))); amount.dataset.lineAmount = String(index);
                cell(amount, 'num');
            }
            const actions = document.createElement('div'); actions.className = 'apw-row-actions';
            if (!readonly) {
                if (!line.display_type) actions.append(button('⋯', () => lineDetails(line), 'apw-line-more'));
                actions.append(button('×', () => {state.lines.splice(index, 1); renderLines(); changed();}));
            }
            actions.querySelectorAll('button').forEach(node => {node.setAttribute('aria-label', node.textContent === '⋯' ? 'Line details' : node.textContent === '×' ? 'Remove line' : node.textContent === '↑' ? 'Move line up' : 'Move line down'); node.title = node.getAttribute('aria-label');});
            cell(actions); host.append(row);
        });
        decorateLineGrid(host.closest('table'),{editor:'purchase',editable:!readonly,entrySelector:'[data-grid-entry]',onAppend:()=>{if(isEmptyDraftLine(state.lines.at(-1)))return false;moveGrid(state.lines.length-1,6,1);},onReorder:(from,to)=>{const [line]=state.lines.splice(from,1);if(line){state.lines.splice(to,0,line);renderLines();changed();}}});
        if (focus) {
            const row = host.querySelector('[data-grid-row="' + focus.row + '"]');
            const cell = row?.querySelector('[data-grid-column="' + focus.column + '"]');
            const target = focus.description ? cell?.querySelector('.apw-description') : cell?.querySelector('[data-grid-entry]');
            if (target && !target.disabled) {
                if (focus.query !== null && !state.lines[focus.row]?.product_id) target.value = focus.query;
                target.dataset.suppressLookupOnce = '1'; target.focus({preventScroll: true});
                if (typeof focus.start === 'number' && target.setSelectionRange && target.type !== 'number') {
                    try {target.setSelectionRange(focus.start, focus.end);} catch (_) { /* date/number control */ }
                }
            }
        }
    }
    function focusGrid(rowIndex, column) {
        const node = byId('apw-lines').querySelector('[data-grid-row="' + rowIndex + '"] [data-grid-column="' + column + '"] [data-grid-entry]');
        if (node && !node.disabled) {node.focus(); node.select?.(); node.scrollIntoView({block: 'nearest', inline: 'nearest'}); return true;}
        return false;
    }
    function moveGrid(rowIndex, column, direction) {
        const host = byId('apw-lines');
        const entries = [...host.querySelectorAll('[data-grid-entry]')].filter(n => !n.disabled);
        const index = entries.findIndex(n => Number(n.closest('[data-grid-row]').dataset.gridRow) === rowIndex && Number(n.closest('td').dataset.gridColumn) === column);
        const next = entries[index + direction];
        if (next) {next.focus(); next.select?.(); next.scrollIntoView({block: 'nearest', inline: 'nearest'}); return;}
        if (direction > 0 && !readonly && state.lines[rowIndex]?.product_id) {
            state.lines.push(blankLine()); changed(); renderLines(); focusGrid(state.lines.length - 1, 0);
        }
    }
    byId('apw-lines').addEventListener('keydown', event => {
        if (event.key !== 'Enter' || event.defaultPrevented || event.isComposing || event.target.closest('.apw-options') || readonly) return;
        if (event.ctrlKey && event.target.tagName === 'TEXTAREA') return;
        const row = event.target.closest('[data-grid-row]'), cell = event.target.closest('td');
        if (!row || !cell || !event.target.matches('[data-grid-entry], .apw-description')) return;
        event.preventDefault(); moveGrid(Number(row.dataset.gridRow), Number(cell.dataset.gridColumn), event.shiftKey ? -1 : 1);
    });
    function lineDetails(line) {
        const view = modal('Line Details'), grid = document.createElement('div'); grid.className = 'apw-form-grid';
        view.body.append(grid);
        field('Expected Arrival', input(line.date_planned, 'datetime-local', value => {line.date_planned = value;}), grid);
        view.body.append(text('p', `Received: ${line.qty_received || 0} · Billed: ${line.qty_invoiced || 0}`));
        if (line.absar_expense_account_id) view.body.append(text('p', 'This saved line has a legacy account override. Selecting its product again applies the product account.', 'apw-help'));
        view.foot.append(button('Done', () => view.dialog.close(), 'btn btn-primary'));
    }
    function moveLine(index, offset) {
        const dest = index + offset; if (dest < 0 || dest >= state.lines.length) return;
        [state.lines[index], state.lines[dest]] = [state.lines[dest], state.lines[index]];
        changed(); renderLines();
    }
    function renderTotals() {
        const host = byId('apw-totals'); host.replaceChildren();
        const untaxed = state.lines.filter(l => !l.display_type).reduce((sum, l) => sum + l.product_qty * l.price_unit * (1 - (l.discount || 0) / 100), 0);
        const empty = !calculationRows(state.lines).some(line => !line.display_type);
        const values = empty ? [0,0,0] : totals ? [totals.untaxed,totals.tax,totals.total] : [null,null,null];
        for (const [index, label] of ['Untaxed Amount', 'Taxes', 'Total'].entries()) {
            const row = text('p', label); row.append(text('strong', values[index] === null ?
                (totalsPending ? 'Calculating…' : '—') : money(values[index]))); host.append(row);
        }
        host.setAttribute('aria-busy', String(totalsPending && !empty));
        host.append(text('small', totalsPending && !empty ? 'Updating…' :
            (totals?.currency || labels.currency_id?.label || ''), 'apw-help'));
    }
    async function recalculate() {
        if(pendingComputations)return;
        const data=payload(), lines=data.lines;
        const missing=[];
        if(!state.currency_id)missing.push('currency');
        if(!state.picking_type_id)missing.push('operation type');
        if(lines.some(line=>!line.display_type&&(!line.product_id||!line.product_uom||!(line.product_qty>0))))missing.push('product, unit and positive quantity');
        if(missing.length){totalsPending=false;renderTotals();status.textContent='Choose '+missing.join(', ')+' to calculate totals.';return;}
        const seq = ++previewSequence;
        totalsPending=true;renderTotals();
        try {
            const response = await post('/preview', data);
            if (seq !== previewSequence) return;
            totals = response; totalsPending = false;status.textContent=state.partner_id?'':'Select a vendor before saving or submitting this order.';clearError();
            response.lines.forEach((native, index) => {
                const row=lines[index];if(row&&state.lines.includes(row)){row.price_subtotal=native.price_subtotal;row.price_total=native.price_total;row._amountKey=amountKey(row);}
            });
            root.querySelectorAll('[data-line-amount]').forEach(node=>{const row=state.lines[Number(node.dataset.lineAmount)];if(row)node.textContent=lineAmount(row)===null?'—':money(lineAmount(row));});
            renderTotals();
        } catch(error) {if(seq===previewSequence){totalsPending=false;renderTotals();throw error;}}
    }
    function modal(title) {
        const dialog = document.createElement('dialog'); dialog.className = 'apw-dialog';
        const head = document.createElement('div'); head.className = 'apw-heading';
        head.append(text('h3', title), button('Close', () => dialog.close()));
        dialog.append(head);
        const body = document.createElement('div'); dialog.append(body);
        const foot = document.createElement('div'); foot.className = 'apw-actions'; dialog.append(foot);
        const previousFocus = document.activeElement;
        dialog.addEventListener('close', () => {dialog.querySelectorAll('.apw-lookup').forEach(node => node.dispatchEvent(new Event('apw-dispose'))); dialog.remove(); if (previousFocus?.isConnected) previousFocus.focus();});
        root.append(dialog); dialog.showModal();
        return {dialog, body, foot};
    }
    function ask(message) {
        return new Promise(resolve=>{const view=modal('Confirm action');let settled=false;
            const finish=value=>{if(!settled){settled=true;resolve(value);}view.dialog.close();};
            view.body.append(text('p',message));view.foot.append(button('Cancel',()=>finish(false)),button('Continue',()=>finish(true),'btn btn-primary'));
            view.dialog.addEventListener('close',()=>{if(!settled){settled=true;resolve(false);}});
        });
    }
    function analyticDialog(line) {
        const view = modal('Analytic Distribution');
        view.body.append(text('p', 'Allocate each plan to 100%. A row can combine one account from each plan.', 'apw-help'));
        const rows = Object.entries(line.analytic_distribution || {}).map(([key, pct]) => ({
            accounts: key.split(',').map(id => line.analytic_labels?.[id] || {id: Number(id), label: id}), pct
        }));
        if (!rows.length) rows.push({accounts: [], pct: 100});
        const table = document.createElement('div'); view.body.append(table);
        const message = text('p', '', 'text-danger'); view.body.append(message);
        function draw() {
            table.replaceChildren();
            rows.forEach((r, i) => {
                const row = document.createElement('div'); row.className = 'apw-allocation';
                const accounts = document.createElement('div');
                for (const a of r.accounts) {
                    const chip = text('span', a.label + (a.plan ? ' · ' + a.plan : ''), 'apw-chip');
                    if (!readonly) chip.append(button('×', () => {r.accounts = r.accounts.filter(x => x.id !== a.id); draw();}, 'apw-chip-remove'));
                    accounts.append(chip);
                }
                if (!readonly) accounts.append(lookup('analytic', null, item => {
                    if (!item) return;
                    if (r.accounts.some(a => a.id === item.id || (a.plan && a.plan === item.plan))) {message.textContent = 'Use one account per plan in each row.'; return;}
                    r.accounts.push(item); message.textContent = ''; draw();
                }));
                const percent = input(r.pct, 'number', v => {r.pct = Number(v);}); percent.min = '0'; percent.max = '100'; percent.setAttribute('aria-label', 'Allocation percentage');
                row.append(accounts, percent, text('span', '%'));
                if (!readonly) row.append(button('×', () => {rows.splice(i, 1); draw();}));
                table.append(row);
            });
        }
        draw();
        if (!readonly) {
            view.foot.append(button('Add a Line', () => {rows.push({accounts: [], pct: 100}); draw();}));
            view.foot.append(button('Apply', () => {
                const distribution = {}, accountLabels = {}, sums = {};
                for (const row of rows) {
                    if (!row.accounts.length && !row.pct) continue;
                    if (!row.accounts.length || !Number.isFinite(row.pct) || row.pct <= 0 || row.pct > 100) {message.textContent = 'Every row needs an account and a percentage greater than zero, up to 100.'; return;}
                    const key = row.accounts.map(a => a.id).sort((a, b) => a - b).join(',');
                    if (key in distribution) {message.textContent = 'Combine duplicate account rows.'; return;}
                    distribution[key] = row.pct;
                    for (const a of row.accounts) {accountLabels[a.id] = a; const plan = a.plan || a.id; sums[plan] = (sums[plan] || 0) + row.pct;}
                }
                if (Object.values(sums).some(n => Math.abs(n - 100) > 0.01)) {message.textContent = 'Each used plan must total 100%.'; return;}
                line.analytic_distribution = distribution; line.analytic_labels = accountLabels;
                changed(); renderLines(); view.dialog.close();
            }, 'btn btn-primary'));
            view.foot.append(button('Clear distribution', () => {line.analytic_distribution = {}; line.analytic_labels = {}; changed(); renderLines(); view.dialog.close();}));
        }
    }
    function catalogDialog() {
        const view = modal('Product Catalog');
        const search = input('', 'search', () => {});
        search.setAttribute('aria-label', 'Search catalog');
        search.placeholder = 'Search product name or internal reference';
        const cards = document.createElement('div'); cards.className = 'apw-catalog';
        const message = text('p', '', 'apw-help');
        let offset = 0, sequence = 0, timer;
        const more = button('Load more', () => load(false));
        async function load(reset) {
            const seq = ++sequence;
            if (reset) {offset = 0; cards.replaceChildren();}
            more.disabled = true;
            try {
                const result = await post('/lookup', {kind: 'product', q: search.value, company_id: state.company_id, offset});
                if (seq !== sequence) return;
                for (const item of result.items) {
                    const card = document.createElement('div'); card.className = 'apw-catalog-card';
                    const add = button('Add', async () => {
                        add.disabled = true;
                        const line = blankLine(); state.lines.push(line); changed();
                        await defaultsFor(line, item);
                        message.textContent = 'Added: ' + item.label;
                        add.disabled = false;
                    }, 'btn btn-outline-primary');
                    card.append(text('strong', item.label), add); cards.append(card);
                }
                offset += result.items.length; more.hidden = !result.more;
                if (!offset) message.textContent = 'No matching products.';
            } catch (error) {message.textContent = error.message;}
            finally {more.disabled = false;}
        }
        search.addEventListener('input', () => {clearTimeout(timer); timer = setTimeout(() => load(true), 220);});
        view.body.append(search, message, cards); view.foot.append(more);
        load(true);
    }
    async function productDialog() {
        const ui = createPurchaseUI({root, post, companyId: state.company_id});
        await openPurchaseProductDialog({...ui, post, companyId: state.company_id, onCreate: async item => {
            const line = blankLine(); state.lines.push(line);
            changed(); await defaultsFor(line, item);
        }});
    }
    function renderAttachments() {
        const host = byId('apw-attachments'); host.replaceChildren();
        for (const attachment of boot.attachments || []) {
            const link = text('a', attachment.name, 'apw-chip');
            link.href = '/my/employee/purchase/' + boot.id + '/attachments/' + attachment.id;
            host.append(link);
        }
        if (!host.childNodes.length) host.append(text('p', 'No quotation PDFs attached.', 'apw-help'));
    }
    async function uploadQuotation() {
        const file = byId('apw-quotation-file')?.files[0];
        if (!file || !file.name.toLowerCase().endsWith('.pdf') || file.size > 1400000) throw new Error('Choose a PDF no larger than 1.4 MB.');
        const data = await new Promise((resolve, reject) => {
            const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('Cannot read the PDF.')); reader.readAsDataURL(file);
        });
        const result = await post('/' + boot.id + '/quotation-upload', {name:file.name, data, version:boot.version});
        boot.version = result.version; boot.attachments ||= []; boot.attachments.push(result);
        byId('apw-quotation-file').value = ''; renderAttachments();
    }
    async function decision(action) {
        let note = '';
        if (action === 'return') {
            note = await new Promise(resolve => {
                const view = modal('Return for Correction');
                const description = document.createElement('textarea'); description.className = 'form-control';
                description.rows = 4; description.maxLength = 2000; description.setAttribute('aria-label', 'Correction required');
                view.body.append(text('p', 'Explain what the preparer should correct.'), description);
                const message = text('p', '', 'text-danger'); view.body.append(message);
                view.foot.append(button('Return Purchase Order', () => {
                    if (!description.value.trim()) {message.textContent = 'A correction note is required.'; return;}
                    resolve(description.value.trim()); view.dialog.close();
                }, 'btn btn-primary'), button('Cancel', () => view.dialog.close()));
                view.dialog.addEventListener('close', () => resolve(null)); description.focus();
            });
            if (note === null) return;
        }
        if (action === 'approve' || action === 'confirm' || action === 'approve_confirm') {
            const confirmed = await new Promise(resolve => {
                const view = modal('Approve Purchase Order');
                view.body.append(text('p', 'Approve this purchase order? It will become a confirmed PO and Odoo will run the purchase workflow.'));
                view.foot.append(button('Approve', () => {resolve(true); view.dialog.close();}, 'btn btn-primary'), button('Cancel', () => view.dialog.close()));
                view.dialog.addEventListener('close', () => resolve(false));
            });
            if (!confirmed) return;
        }
        const response = await post('/' + boot.id + '/decision', {action, note, version: boot.version});
        dirty = false; window.location.assign(response.url);
    }
    let draftJob=null,draftNavigate=true;
    function saveDraft(options={}){
        if(draftJob){if(options.navigate===false)draftNavigate=false;return draftJob;}
        draftNavigate=options.navigate!==false;const job=persistDraft(options);draftJob=job;job.then(()=>{draftJob=null;},()=>{draftJob=null;});return job;
    }
    async function persistDraft({submit=false,navigate=true}={}){
        if(busy)return false;
        busy=true;root.classList.add('apw-busy');status.textContent='Saving…';clearError();
        try{
            if(!state.partner_id)throw new Error('Choose a vendor from the search results before saving.');
            if(!state.currency_id)throw new Error('Choose a currency before saving.');
            while(defaultJobs.size)await Promise.all([...defaultJobs]);
            const result=await post('/save',{...payload(),submit});dirty=false;
            if(result.id){boot.id=result.id;boot.version=result.version;state.lines=result.lines;state.lines.forEach(line=>{line._manualPrice=true;line._manualTaxes=true;});}
            if(draftNavigate)window.location.assign(result.url);
            else{window.history?.replaceState(null,'',result.url);status.textContent='Draft saved.';renderLines();}
            return true;
        }catch(error){status.textContent='';showError(error);return false;}
        finally{busy=false;root.classList.remove('apw-busy');}
    }
    root.addEventListener('click', async event => {
        const tab = event.target.closest('[data-tab]');
        if (tab) {
            root.querySelectorAll('[data-tab]').forEach(t => t.setAttribute('aria-selected', String(t === tab)));
            root.querySelectorAll('[data-panel]').forEach(p => {p.hidden = p.dataset.panel !== tab.dataset.tab;});
            return;
        }
        const action = event.target.closest('[data-action]')?.dataset.action;
        if (!action || busy) return;
        clearError();
        try {
            if (['add', 'section', 'note'].includes(action)) {
                state.lines.push(blankLine(action === 'section' ? 'line_section' : action === 'note' ? 'line_note' : ''));
                changed(); renderLines(); return;
            }
            if (action === 'catalog') {catalogDialog(); return;}
            if (action === 'product') {await productDialog(); return;}
            if(action==='save'||action==='submit'){await saveDraft({submit:action==='submit'});return;}
            busy = true; root.classList.add('apw-busy'); status.textContent = 'Working…';
            if (action === 'receive') {
                const ui = createPurchaseUI({root, post, companyId: state.company_id});
                await openPurchaseReceiptDialog({post, poId: boot.id, ui, onDone: result => window.location.assign(result.url)});
            } else if (action === 'create_bill') {
                if(await ask('Create a draft vendor bill using this purchase order’s currently billable quantities?')){const result=await post('/'+boot.id+'/create-bill',{version:boot.version});dirty=false;window.location.assign(result.url);}
            } else if (action === 'upload') await uploadQuotation();
            else if (action === 'recalculate') await recalculate();
            else await decision(action);
        } catch (error) {showError(error);}
        finally {busy = false; root.classList.remove('apw-busy'); if(status.textContent==='Working…')status.textContent = '';}
    });
    byId('apw-notes').value = state.notes || '';
    byId('apw-notes').addEventListener('input', event => {state.notes = event.target.value; changed();});
    installDraftNavigation({isDirty:()=>!readonly&&dirty,save:()=>saveDraft({navigate:false}),onError:error=>{if(errorBox.hidden)showError(error);}});
    state.lines.forEach(line => {line._manualPrice = Boolean(line.id);line._manualTaxes=Boolean(line.id);});
    renderHeader(); renderLines(); renderTotals(); renderAttachments();
    if (!readonly && state.partner_id && state.lines.some(l => !l.display_type)) recalculate().catch(showError);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startPurchaseWorkspace);
else startPurchaseWorkspace();
