/** @odoo-module **/
export async function openPurchaseProductDialog({post, modal, field, input, lookup, button, text, companyId,
        onCreate = async () => {}, saveLabel, productId = null, initialName = ''}) {
    const editing = Boolean(productId);
    const defaults = await post(editing ? '/product-read' : '/product-defaults', {company_id: companyId, ...(editing ? {id: productId} : {})});
    const readonly = editing && !defaults.can_edit;
    const view = modal(editing ? 'Product: ' + defaults.name : 'Create Purchasing Product');
    if (editing && defaults.shared && !readonly) view.body.append(text('p', 'Shared product. General details apply across companies; the expense account is saved for the selected company.', 'apw-help'));
    const values = {company_id: companyId, type: defaults.type || 'consu', is_storable: Boolean(defaults.is_storable),
        purchase_method: defaults.purchase_method || 'receive', name: defaults.name || initialName,
        ...(editing ? {id: productId, version: defaults.version} : {})};
    for (const key of ['categ_id', 'uom_id', 'uom_po_id', 'property_account_expense_id']) values[key] = defaults[key]?.id || 0;
    const selectedTaxes = new Map((defaults.supplier_taxes || []).filter(Boolean).map(t => [t.id, t]));
    const grid = document.createElement('div'); grid.className = 'apw-form-grid apw-product-grid'; view.body.append(grid);
    const name = field('Product Name *', input(values.name, 'text', v => {values.name = v;}), grid);
    const type = document.createElement('select'); type.className = 'form-select';
    for (const [v, label] of [['consu', 'Goods'], ['service', 'Service']]) {const o = text('option', label); o.value = v; type.append(o);}
    type.value = values.type; type.addEventListener('change', () => {values.type = type.value;}); field('Product Type', type, grid);
    const track = document.createElement('input'); track.type = 'checkbox'; track.checked = values.is_storable;
    track.addEventListener('change', () => {values.is_storable = track.checked;}); field('Track Inventory (Goods)', track, grid);
    field('Category *', lookup('category', defaults.categ_id, item => {values.categ_id = item?.id || 0;}), grid);
    field('Unit of Measure *', lookup('uom', defaults.uom_id, item => {values.uom_id = item?.id || 0;}), grid);
    field('Purchase Unit', lookup('uom', defaults.uom_po_id, item => {values.uom_po_id = item?.id || 0;}), grid);
    for (const [key, label, kind] of [['default_code', 'Internal Reference', 'text'], ['barcode', 'Barcode', 'text'],
            ['standard_price', 'Cost', 'number'], ['description_purchase', 'Purchase Description', 'text']]) {
        values[key] = defaults[key] ?? '';
        field(label, input(values[key], kind, value => {values[key] = value;}), grid);
    }
    field('Expense Account', lookup('account', defaults.property_account_expense_id,
        item => {values.property_account_expense_id = item?.id || 0;}), grid,
        'Leave empty to use the category account.' + (defaults.category_expense_account ? ' ' + defaults.category_expense_account : ''));
    const policy = document.createElement('select'); policy.className = 'form-select';
    for (const [v, label] of [['receive', 'On received quantities'], ['purchase', 'On ordered quantities']]) {const o = text('option', label); o.value = v; policy.append(o);}
    policy.value = values.purchase_method; policy.addEventListener('change', () => {values.purchase_method = policy.value;}); field('Bill Control Policy', policy, grid);
    const taxHost = document.createElement('div'), taxSummary = text('p', ''); taxHost.append(taxSummary);
    const renderTaxes = () => {taxSummary.textContent = [...selectedTaxes.values()].map(t => t.label).join(', ') || 'No purchase taxes.'; values.supplier_taxes_id = [...selectedTaxes.keys()];};
    renderTaxes();
    taxHost.append(lookup('tax', null, item => {if (item) {selectedTaxes.set(item.id, item); renderTaxes();}}));
    taxHost.append(button('No purchase tax', () => {selectedTaxes.clear(); renderTaxes();})); field('Purchase Taxes', taxHost, grid);
    if (readonly) {
        grid.querySelectorAll('input, select, button, textarea').forEach(node => {node.disabled = true;});
        view.foot.append(button('Close', () => view.dialog.close())); return;
    }
    const message = text('p', '', 'text-danger'); view.body.append(message);
    let savedItem = null;
    const save = button(saveLabel || (editing ? 'Save' : 'Create and Add'), async () => {
        save.disabled = true;
        try {
            if (!savedItem) {
                if (!values.name?.trim()) throw new Error('Enter a product name.');
                for (const [key, label] of [['categ_id', 'Category'], ['uom_id', 'Unit of Measure']]) {
                    if (!Number.isSafeInteger(values[key]) || values[key] <= 0) throw new Error('Select ' + label + ' from the list.');
                }
                savedItem = await post(editing ? '/product-update' : '/product-create', values);
            }
            view.dialog.close(); await onCreate(savedItem);
        } catch (error) {message.textContent = error.message; save.disabled = false;}
    }, 'btn btn-primary');
    view.foot.append(save, button('Discard', () => view.dialog.close())); name.focus();
}
