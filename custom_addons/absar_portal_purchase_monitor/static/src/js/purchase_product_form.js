/** @odoo-module **/
export async function openPurchaseProductDialog({post, modal, field, input, lookup, button, text, companyId, onCreate, saveLabel = 'Create and Add'}) {
        const defaults = await post('/product-defaults', {company_id: companyId});
        const view = modal('Create Purchasing Product');
        const values = {company_id: companyId, type: 'consu', is_storable: false, purchase_method: 'receive'};
        for (const key of ['categ_id', 'uom_id', 'uom_po_id']) values[key] = defaults[key]?.id || 0;
        values.purchase_method = defaults.purchase_method || 'receive';
        values.supplier_taxes_id = defaults.supplier_taxes.map(t => t.id);
        const selectedTaxes = new Map(defaults.supplier_taxes.map(t => [t.id, t]));
        const grid = document.createElement('div'); grid.className = 'apw-form-grid'; view.body.append(grid);
        field('Product Name *', input('', 'text', v => {values.name = v;}), grid);
        const type = document.createElement('select'); type.className = 'form-select';
        for (const [v, label] of [['consu', 'Goods'], ['service', 'Service']]) {const o = text('option', label); o.value = v; type.append(o);}
        type.addEventListener('change', () => {values.type = type.value;}); field('Product Type', type, grid);
        const track = document.createElement('input'); track.type = 'checkbox'; track.addEventListener('change', () => {values.is_storable = track.checked;}); field('Track Inventory (Goods)', track, grid);
        field('Category *', lookup('category', defaults.categ_id, item => {values.categ_id = item?.id || 0;}), grid);
        field('Unit of Measure *', lookup('uom', defaults.uom_id, item => {values.uom_id = item?.id || 0;}), grid);
        field('Purchase Unit', lookup('uom', defaults.uom_po_id, item => {values.uom_po_id = item?.id || 0;}), grid, 'Defaults to the product unit.');
        field('Internal Reference', input('', 'text', v => {values.default_code = v;}), grid);
        field('Barcode', input('', 'text', v => {values.barcode = v;}), grid);
        field('Cost', input('', 'number', v => {values.standard_price = v;}), grid);
        field('Purchase Description', input('', 'text', v => {values.description_purchase = v;}), grid);
        field('Expense Account', lookup('account', null, item => {values.property_account_expense_id = item?.id || 0;}), grid, 'Leave empty to use the category expense account.');
        const policy = document.createElement('select'); policy.className = 'form-select';
        for (const [v, label] of [['receive', 'On received quantities'], ['purchase', 'On ordered quantities']]) {const o = text('option', label); o.value = v; policy.append(o);}
        policy.value = values.purchase_method;
        policy.addEventListener('change', () => {values.purchase_method = policy.value;}); field('Bill Control Policy', policy, grid);
        const taxHost = document.createElement('div');
        const taxSummary = text('p', ''); taxHost.append(taxSummary);
        const renderTaxes = () => {taxSummary.textContent = [...selectedTaxes.values()].map(t => t.label).join(', ') || 'No purchase taxes.'; values.supplier_taxes_id = [...selectedTaxes.keys()];};
        renderTaxes();
        taxHost.append(lookup('tax', null, item => {if (!item) return; selectedTaxes.set(item.id, item); renderTaxes();}));
        taxHost.append(button('No purchase tax', () => {selectedTaxes.clear(); renderTaxes();}));
        field('Purchase Taxes', taxHost, grid);
        const message = text('p', '', 'text-danger'); view.body.append(message);
        const save = button(saveLabel, async () => {
            save.disabled = true;
            try {
                if (!values.name?.trim()) throw new Error('Enter a product name.');
                for (const [key, label] of [['categ_id', 'Category'], ['uom_id', 'Unit of Measure']]) {
                    if (!Number.isSafeInteger(values[key]) || values[key] <= 0) throw new Error('Select ' + label + ' from the list.');
                }
                const item = await post('/product-create', values);
                // Product creation succeeded. A subsequent RFQ default failure
                // must never leave a Create button that creates it a second time.
                view.dialog.close(); await onCreate(item);
            } catch (error) {message.textContent = error.message; save.disabled = false;}
        }, 'btn btn-primary');
        view.foot.append(save);
    }
