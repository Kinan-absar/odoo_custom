/** @odoo-module **/
import { createPurchaseUI } from "./purchase_ui";
import { openPurchaseProductDialog } from "./purchase_product_form";
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
    let totals = boot.totals || null;
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
    const changed = () => {
        dirty = true; previewSequence++; totals = null; renderTotals();
        clearTimeout(previewTimer);
        previewTimer = setTimeout(() => {
            const lines = state.lines.filter(line => !line.display_type);
            if (!busy && !pendingComputations && state.partner_id && state.currency_id && state.picking_type_id &&
                    lines.length && lines.every(line => line.product_id && line.product_qty > 0)) {
                recalculate().catch(showError);
            }
        }, 450);
    };
    const showError = error => {errorBox.textContent = error.message || String(error); errorBox.hidden = false; errorBox.scrollIntoView({block: 'nearest'});};
    const clearError = () => {errorBox.hidden = true; errorBox.textContent = '';};
    async function post(path, payload) {
        const response = await fetch('/my/employee/purchase' + path, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
            body: new URLSearchParams({csrf_token: csrf, payload: JSON.stringify(payload)})
        });
        const type = response.headers.get('content-type') || '';
        if (!type.includes('application/json')) throw new Error('Your session or purchase permission has changed. Reload this page.');
        const result = await response.json();
        if (!response.ok || result.error) throw new Error(result.error || 'The request could not be completed.');
        return result;
    }
    function payload() {return {...state, id: boot.id, version: boot.version};}
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
        node.addEventListener('change', () => {onChange(node.value); changed();});
        return node;
    }
    function button(label, callback, cls = 'btn btn-light') {
        const node = text('button', label, cls);
        node.type = 'button';
        node.addEventListener('click', callback);
        return node;
    }
    function lookup(kind, selected, onSelect, extras = {}) {
        const wrap = document.createElement('div');
        wrap.className = 'apw-lookup';
        const box = document.createElement('input');
        box.className = 'form-control';
        box.value = selected?.label || '';
        box.placeholder = 'Search…';
        box.setAttribute('aria-label', kind + ' search');
        box.setAttribute('role', 'combobox');
        box.setAttribute('aria-expanded', 'false');
        box.autocomplete = 'off';
        box.disabled = readonly;
        const options = document.createElement('div');
        options.className = 'apw-options';
        options.setAttribute('role', 'listbox');
        options.hidden = true;
        options.setAttribute('popover', 'manual');
        const closeOptions = () => {if (typeof options.hidePopover === 'function' && options.matches(':popover-open')) options.hidePopover(); options.hidden = true; box.setAttribute('aria-expanded', 'false');};
        const openOptions = () => {
            options.hidden = false;
            const rect = box.getBoundingClientRect();
            options.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - 300)) + 'px';
            options.style.top = Math.min(rect.bottom + 2, window.innerHeight - 220) + 'px';
            options.style.width = Math.min(Math.max(rect.width, 280), window.innerWidth - 24) + 'px';
            if (typeof options.showPopover === 'function') options.showPopover(); box.setAttribute('aria-expanded', 'true');
        };
        let timer, sequence = 0, selectedId = selected?.id;
        async function search() {
            if (readonly) return;
            const seq = ++sequence;
            options.replaceChildren(text('div', 'Searching…', 'apw-help'));
            openOptions();
            try {
                const result = await post('/lookup', {kind, q: box.value, company_id: state.company_id, project_id: state.project_id, ...extras});
                if (seq !== sequence) return;
                options.replaceChildren();
                for (const item of result.items) {
                    const choice = button(item.label + (item.plan ? ' · ' + item.plan : ''), () => {
                        box.value = item.label; selectedId = item.id;
                        closeOptions();
                        onSelect(item); changed();
                    }, 'apw-option');
                    choice.setAttribute('role', 'option');
                    options.append(choice);
                }
                if (!result.items.length) options.append(text('div', 'No matches', 'apw-help'));
                if (result.more) options.append(text('div', 'Type more to narrow the results.', 'apw-help'));
                options.append(button('Clear selection', () => {
                    box.value = ''; selectedId = null; closeOptions(); onSelect(null); changed();
                }, 'apw-option'));
            } catch (error) {options.replaceChildren(text('div', error.message, 'apw-help'));}
        }
        box.addEventListener('input', () => {
            if (selectedId) {selectedId = null; onSelect(null); changed();}
            clearTimeout(timer); timer = setTimeout(search, 220);
        });
        box.addEventListener('focus', () => {
            if (selectedId) {
                options.replaceChildren(button('Search another selection', () => {box.value = ''; selectedId = null; onSelect(null); search();}, 'apw-option'),
                    button('Clear selection', () => {box.value = ''; selectedId = null; onSelect(null); closeOptions(); changed();}, 'apw-option'));
                openOptions();
            } else search();
        });
        box.addEventListener('keydown', event => {
            if (event.key === 'Escape') {closeOptions();}
            if (event.key === 'ArrowDown') {event.preventDefault(); options.querySelector('button')?.focus();}
            if (event.key === 'Enter') event.preventDefault();
        });
        wrap.addEventListener('focusout', () => setTimeout(() => {
            if (!wrap.contains(document.activeElement)) {closeOptions();}
        }, 100));
        wrap.append(box, options);
        return wrap;
    }
    function headerChoice(host, label, name, kind, hint) {
        field(label, lookup(kind, labels[name], item => {
            state[name] = item?.id || 0; labels[name] = item;
            if (name === 'partner_id' && item) vendorDefaults().catch(showError);
            else if (['currency_id', 'fiscal_position_id'].includes(name) && state.partner_id) repriceAll();
            if (name === 'project_id') {state.material_request_id = 0; labels.material_request_id = null; renderHeader();}
            if (name === 'material_request_id' && item) linkMaterial(item.id).catch(showError);
        }), host, hint);
    }
    function renderHeader() {
        const header = byId('apw-header'), other = byId('apw-other');
        header.replaceChildren(); other.replaceChildren();
        headerChoice(header, 'Vendor *', 'partner_id', 'vendor');
        field(['purchase', 'done'].includes(boot.state) ? 'Order Date' : 'Order Deadline *', input(state.date_order, 'datetime-local', v => {state.date_order = v;}), header);
        field('Vendor Reference', input(state.partner_ref, 'text', v => {state.partner_ref = v;}), header);
        field('Expected Arrival', input(state.date_planned, 'datetime-local', v => {
            state.date_planned = v;
            for (const line of state.lines) if (!line.display_type) line.date_planned = v;
            renderLines();
        }), header, 'Sets the arrival date on all product lines. Individual dates remain editable below.');
        headerChoice(header, 'Material Request', 'material_request_id', 'mr', 'Approved requests from your assigned projects.');
        if (!readonly && state.material_request_id) {
            header.append(button('Import Material Request lines', () => importMaterial().catch(showError), 'btn btn-outline-secondary'));
        }
        headerChoice(header, 'Project', 'project_id', 'project', 'Uses employee work location project assignments.');
        headerChoice(header, 'Currency *', 'currency_id', 'currency');
        headerChoice(other, 'Buyer', 'user_id', 'buyer');
        const company = document.createElement('select'); company.className = 'form-select';
        company.disabled = readonly || Boolean(boot.id);
        for (const c of boot.companies) {const o = text('option', c.label); o.value = c.id; company.append(o);}
        company.value = state.company_id;
        company.addEventListener('change', () => {
            if (dirty && !window.confirm('Changing company clears vendor, project, accounting selections and lines. Continue?')) {company.value = state.company_id; return;}
            state.company_id = Number(company.value); state.lines = []; state.material_request_id = 0;
            for (const k of Object.keys(labels)) {labels[k] = null; state[k] = 0;}
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
        if (state.lines.length && !window.confirm('Replace current draft lines with the selected Material Request materials?')) return;
        const info = await post('/mr-info', {company_id: state.company_id, mr_id: state.material_request_id});
        state.project_id = info.project.id; labels.project_id = info.project;
        state.lines = info.lines; changed(); renderHeader(); renderLines();
        repriceAll();
    }
    let vendorSequence = 0;
    async function vendorDefaults() {
        const seq = ++vendorSequence;
        pendingComputations++;
        try {
            const result = await post('/vendor-defaults', {partner_id: state.partner_id, company_id: state.company_id});
            if (seq !== vendorSequence) return;
            for (const [name, item] of Object.entries(result.selected)) {labels[name] = item; state[name] = item?.id || 0;}
            if (!state.notes) {state.notes = result.notes; byId('apw-notes').value = state.notes;}
            renderHeader(); changed(); repriceAll();
        } finally {pendingComputations--;}
    }
    async function reprice(line) {
        if (!line.product_id || !state.partner_id) return;
        const seq = (line._priceSequence || 0) + 1; line._priceSequence = seq;
        pendingComputations++;
        try {
            const result = await post('/preview', {...payload(), defaults: true, lines: [line]});
            if (line._priceSequence !== seq) return;
            const native = result.lines[0];
            if (!line.product_uom) {line.product_uom = native.product_uom; line.uom_label = native.uom_label;}
            if (!line.name) line.name = native.name;
            if (!line.date_planned) line.date_planned = native.date_planned;
            if (!line._manualPrice) {line.price_unit = native.price_unit; line.discount = native.discount;}
            line.taxes_id = native.taxes_id; line.taxes = native.taxes;
            line.default_account = native.default_account;
            changed(); renderLines();
        } catch (error) {showError(error);}
        finally {pendingComputations--;}
    }
    function repriceAll() {
        for (const line of state.lines) if (!line.display_type) reprice(line);
    }
    function blankLine(display = '') {
        return {id: 0, display_type: display, product_id: 0, product_label: '', name: '',
            product_qty: 1, product_uom: 0, price_unit: 0, discount: 0, taxes_id: [], taxes: [],
            analytic_distribution: {}, analytic_labels: {}, date_planned: state.date_planned || '',
            absar_expense_account_id: 0, account_label: '', default_account: ''};
    }
    async function defaultsFor(line, product) {
        if (!product) {line.product_id = 0; line.product_label = ''; return;}
        if (!state.partner_id) {
            line.product_id = product.id; line.product_label = product.label; line.product_uom = 0;
            changed(); renderLines(); return;
        }
        const sequence = (line._sequence || 0) + 1; line._sequence = sequence;
        pendingComputations++;
        line.product_id = product.id; line.product_label = product.label;
        line.product_uom = 0;
        try {
            const response = await post('/preview', {...payload(), defaults: true, lines: [line]});
            if (line._sequence !== sequence) return;
            const ident = line.id;
            Object.assign(line, response.lines[0], {id: ident, _sequence: sequence, _manualPrice: false});
            if (state.date_planned) line.date_planned = state.date_planned;
            changed(); renderLines();
        } catch (error) {showError(error);}
        finally {pendingComputations--;}
    }
    function renderLines() {
        const host = byId('apw-lines'); host.replaceChildren();
        if (!state.lines.length) {const row = document.createElement('tr'), cell = text('td', 'Add a product, section or note.', 'apw-empty'); cell.colSpan = 9; row.append(cell); host.append(row);}
        state.lines.forEach((line, index) => {
            const row = document.createElement('tr');
            function cell(node, className = '') {const td = document.createElement('td'); td.className = className; td.append(node); row.append(td); return td;}
            if (line.display_type) {
                const label = input(line.name, 'text', v => {line.name = v;});
                const td = cell(label, line.display_type === 'line_section' ? 'apw-section' : 'apw-note'); td.colSpan = 8;
            } else {
                if (!line.product_id) row.classList.add('apw-products-missing');
                const productCell = document.createElement('div');
                if (!line.product_id && line.name) productCell.append(text('small', 'Select a product for this material', 'apw-help'));
                productCell.append(lookup('product', {id: line.product_id, label: line.product_label}, item => defaultsFor(line, item)));
                const description = document.createElement('textarea'); description.className = 'form-control apw-description'; description.rows = 2;
                description.value = line.name; description.disabled = readonly; description.setAttribute('aria-label', 'Line description');
                description.addEventListener('change', () => {line.name = description.value; changed();});
                productCell.append(description); cell(productCell);
                const analytic = document.createElement('div');
                const descriptionText = Object.entries(line.analytic_distribution || {}).map(([key, pct]) =>
                    key.split(',').map(id => line.analytic_labels?.[id]?.label || id).join(' + ') + ': ' + pct + '%').join('; ');
                analytic.append(button(descriptionText || (readonly ? '—' : 'Set distribution'), () => analyticDialog(line), 'btn btn-link apw-analytic'));
                cell(analytic);
                cell(input(line.product_qty, 'number', v => {line.product_qty = Number(v); reprice(line);}), 'num');
                cell(lookup('uom', {id: line.product_uom, label: line.uom_label}, item => {
                    line.product_uom = item?.id || 0; line.uom_label = item?.label || ''; if (item) reprice(line);
                }, {product_id: line.product_id}));
                cell(input(line.price_unit, 'number', v => {line.price_unit = Number(v); line._manualPrice = true;}), 'num');
                cell(input(line.discount || 0, 'number', v => {line.discount = Number(v);}), 'num');
                const tax = document.createElement('div');
                for (const selected of line.taxes || []) {
                    const chip = text('span', selected.label, 'apw-chip');
                    if (!readonly) chip.append(button('×', () => {line.taxes_id = line.taxes_id.filter(id => id !== selected.id); line.taxes = line.taxes.filter(t => t.id !== selected.id); changed(); renderLines();}, 'apw-chip-remove'));
                    tax.append(chip);
                }
                if (!readonly) tax.append(lookup('tax', null, item => {
                    if (item && !line.taxes_id.includes(item.id)) {line.taxes_id.push(item.id); line.taxes.push(item); changed(); renderLines();}
                }));
                cell(tax);
                cell(text('span', money(line.price_subtotal ?? line.product_qty * line.price_unit * (1 - (line.discount || 0) / 100))), 'num');
            }
            const actions = document.createElement('div'); actions.className = 'apw-row-actions';
            if (!readonly) {
                actions.append(button('↑', () => moveLine(index, -1)), button('↓', () => moveLine(index, 1)),
                    button('Remove', () => {state.lines.splice(index, 1); changed(); renderLines();}));
            }
            cell(actions); host.append(row);
            if (!line.display_type) {
                const extraRow = document.createElement('tr'), td = document.createElement('td'); td.colSpan = 9;
                const details = document.createElement('details');
                details.append(text('summary', 'Arrival · Expense account · Received / Billed'));
                const grid = document.createElement('div'); grid.className = 'apw-form-grid apw-line-details';
                field('Expected Arrival', input(line.date_planned, 'datetime-local', v => {line.date_planned = v;}), grid);
                field('Expense Account', lookup('account', {id: line.absar_expense_account_id, label: line.account_label}, item => {
                    line.absar_expense_account_id = item?.id || 0; line.account_label = item?.label || '';
                }), grid, 'Automatic: ' + (line.default_account || 'product/category expense account'));
                grid.append(text('p', `Received: ${line.qty_received || 0} · Billed: ${line.qty_invoiced || 0}`));
                if (!readonly) grid.append(button('Apply vendor defaults', () => defaultsFor(line, {id: line.product_id, label: line.product_label})));
                details.append(grid); td.append(details); extraRow.append(td); host.append(extraRow);
            }
        });
    }
    function moveLine(index, offset) {
        const dest = index + offset; if (dest < 0 || dest >= state.lines.length) return;
        [state.lines[index], state.lines[dest]] = [state.lines[dest], state.lines[index]];
        changed(); renderLines();
    }
    function renderTotals() {
        const host = byId('apw-totals'); host.replaceChildren();
        const untaxed = state.lines.filter(l => !l.display_type).reduce((sum, l) => sum + l.product_qty * l.price_unit * (1 - (l.discount || 0) / 100), 0);
        for (const [label, value] of totals ? [['Untaxed Amount', totals.untaxed], ['Taxes', totals.tax], ['Total', totals.total]] : [['Untaxed estimate', untaxed]]) {
            const row = text('p', label); row.append(text('strong', money(value))); host.append(row);
        }
        host.append(text('small', totals ? totals.currency : 'Tax totals pending recalculation', 'apw-help'));
    }
    async function recalculate() {
        const seq = ++previewSequence;
        const response = await post('/preview', payload());
        if (seq !== previewSequence) return;
        totals = response;
        response.lines.forEach((native, index) => {
            if (state.lines[index]) {state.lines[index].price_subtotal = native.price_subtotal; state.lines[index].price_total = native.price_total;}
        });
        renderLines(); renderTotals();
    }
    function modal(title) {
        const dialog = document.createElement('dialog'); dialog.className = 'apw-dialog';
        const head = document.createElement('div'); head.className = 'apw-heading';
        head.append(text('h3', title), button('Close', () => dialog.close()));
        dialog.append(head);
        const body = document.createElement('div'); dialog.append(body);
        const foot = document.createElement('div'); foot.className = 'apw-actions'; dialog.append(foot);
        const previousFocus = document.activeElement;
        dialog.addEventListener('close', () => {dialog.remove(); previousFocus?.focus();});
        root.append(dialog); dialog.showModal();
        return {dialog, body, foot};
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
                if (!readonly) row.append(button('Remove', () => {rows.splice(i, 1); draw();}));
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
                view.foot.append(button('Return RFQ', () => {
                    if (!description.value.trim()) {message.textContent = 'A correction note is required.'; return;}
                    resolve(description.value.trim()); view.dialog.close();
                }, 'btn btn-primary'), button('Cancel', () => view.dialog.close()));
                view.dialog.addEventListener('close', () => resolve(null)); description.focus();
            });
            if (note === null) return;
        }
        if (action === 'confirm') {
            const confirmed = await new Promise(resolve => {
                const view = modal('Confirm Purchase Order');
                view.body.append(text('p', 'Confirm this independently approved RFQ? Odoo may create receipts and run the installed purchase/signing workflow.'));
                view.foot.append(button('Confirm Purchase Order', () => {resolve(true); view.dialog.close();}, 'btn btn-primary'), button('Cancel', () => view.dialog.close()));
                view.dialog.addEventListener('close', () => resolve(false));
            });
            if (!confirmed) return;
        }
        const response = await post('/' + boot.id + '/decision', {action, note, version: boot.version});
        dirty = false; window.location.assign(response.url);
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
            busy = true; root.classList.add('apw-busy'); status.textContent = 'Working…';
            if (action === 'save' || action === 'submit') {
                if (pendingComputations) throw new Error('Wait for product and vendor defaults to finish loading, then save.');
                const result = await post('/save', {...payload(), submit: action === 'submit'});
                dirty = false; window.location.assign(result.url);
            } else if (action === 'upload') await uploadQuotation();
            else if (action === 'recalculate') await recalculate();
            else await decision(action);
        } catch (error) {showError(error);}
        finally {busy = false; root.classList.remove('apw-busy'); status.textContent = '';}
    });
    byId('apw-notes').value = state.notes || '';
    byId('apw-notes').addEventListener('input', event => {state.notes = event.target.value; changed();});
    window.addEventListener('beforeunload', event => {if (dirty) {event.preventDefault(); event.returnValue = '';}});
    state.lines.forEach(line => {line._manualPrice = Boolean(line.id);});
    renderHeader(); renderLines(); renderTotals(); renderAttachments();
    if (!readonly && state.partner_id && state.lines.some(l => !l.display_type)) recalculate().catch(showError);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startPurchaseWorkspace);
else startPurchaseWorkspace();
