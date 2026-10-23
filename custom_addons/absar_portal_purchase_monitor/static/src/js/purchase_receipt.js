/** @odoo-module **/
export async function openPurchaseReceiptDialog({post, poId, ui, onDone}) {
    const {text, button, input, field, modal} = ui;
    const result = await post('/' + poId + '/receipts', {});
    const view = modal('Receive Products');
    const receipts = result.receipts || [];
    if (!receipts.length) {
        view.body.append(text('p', 'No pending supplier receipts for this purchase order. If the products are already received, return to the PO and create the vendor bill. Services and manual receipt quantities are handled in internal Purchase.'));
        view.foot.append(button('Close', () => view.dialog.close())); return;
    }
    view.body.append(text('p', 'Enter quantities delivered now, then validate the receipt. Remaining quantities stay pending for a later delivery.', 'apw-help'));
    const chooser = document.createElement('select'); chooser.className = 'form-select'; chooser.setAttribute('aria-label', 'Receipt');
    for (const receipt of receipts) {const option = text('option', receipt.name); option.value = String(receipt.id); chooser.append(option);}
    field('Receipt', chooser, view.body);
    const content = document.createElement('div'), message = text('p', '', 'text-danger'); message.setAttribute('role', 'alert');
    view.body.append(content, message);
    let receipt = receipts[0], values = new Map(), inputs = new Map(), saving = false;
    function error(value) {message.textContent = value?.message || String(value);}
    function draw() {
        content.replaceChildren(); message.textContent = ''; values = new Map(); inputs = new Map();
        if (receipt.problem) content.append(text('p', receipt.problem, 'alert alert-warning'));
        if (receipt.backorder_policy === 'never') content.append(text('p', 'Partial receipts require backorders to be enabled for this operation type in Inventory.', 'apw-help'));
        const scroll = document.createElement('div'); scroll.className = 'apw-table-scroll';
        const table = document.createElement('table'); table.className = 'apw-table apw-receipt-lines';
        const head = document.createElement('thead'), heading = document.createElement('tr');
        for (const label of ['Product', 'Remaining on receipt', 'Previously received on PO', 'Receive now', 'Unit']) heading.append(text('th', label));
        head.append(heading); table.append(head);
        const body = document.createElement('tbody'); table.append(body); scroll.append(table); content.append(scroll);
        for (const line of receipt.lines) {
            values.set(line.id, 0);
            const row = document.createElement('tr'), product = text('td', line.product);
            if (!line.lot_ready) product.append(text('small', 'Lot / serial number must be assigned in Inventory first.', 'apw-help'));
            row.append(product, text('td', line.expected, 'num'), text('td', line.already_received, 'num'));
            const qty = input(0, 'number', value => {values.set(line.id, Number(value));});
            qty.min = '0'; qty.max = String(line.expected); qty.setAttribute('aria-label', 'Receive now: ' + line.product);
            qty.disabled = Boolean(receipt.problem) || !line.lot_ready; inputs.set(line.id, qty);
            qty.addEventListener('keydown', event => {
                if (event.key === 'Enter') {event.preventDefault(); const list = [...inputs.values()].filter(n => !n.disabled); const next = list[list.indexOf(qty) + (event.shiftKey ? -1 : 1)]; if (next) {next.focus(); next.select();} else validate.focus();}
            });
            const cell = document.createElement('td'); cell.append(qty); row.append(cell, text('td', line.uom)); body.append(row);
        }
        fill.disabled = Boolean(receipt.problem); validate.disabled = Boolean(receipt.problem);
    }
    const fill = button('Set Remaining Quantities', () => {
        for (const line of receipt.lines) {const node = inputs.get(line.id); if (!node.disabled) {node.value = line.expected; values.set(line.id, line.expected);}}
        message.textContent = '';
    }, 'btn btn-outline-primary');
    const cancel = button('Cancel', () => {if (!saving) view.dialog.close();});
    const validate = button('Validate Receipt', async () => {
        if (saving) return;
        try {
            const quantities = receipt.lines.map(line => ({id: line.id, quantity: values.get(line.id)}));
            if (!quantities.some(line => line.quantity > 0)) throw new Error('Enter at least one received quantity.');
            for (const line of receipt.lines) {
                const quantity = values.get(line.id);
                if (!Number.isFinite(quantity) || quantity < 0 || quantity > line.expected + 1e-9) throw new Error('Enter a quantity between zero and the remaining demand for ' + line.product + '.');
            }
            saving = true; validate.disabled = true; fill.disabled = true; cancel.disabled = true; chooser.disabled = true;
            inputs.forEach(node => {node.disabled = true;}); message.textContent = '';
            const saved = await post('/' + poId + '/receive', {receipt_id: receipt.id, version: receipt.version, quantities});
            view.dialog.close(); await onDone(saved);
        } catch (failure) {error(failure);}
        finally {
            saving = false; validate.disabled = Boolean(receipt.problem); fill.disabled = Boolean(receipt.problem); cancel.disabled = false; chooser.disabled = false;
            for (const line of receipt.lines) inputs.get(line.id).disabled = Boolean(receipt.problem) || !line.lot_ready;
        }
    }, 'btn btn-primary');
    // Prevent closing a dialog while the server is validating its receipt.
    view.dialog.addEventListener('cancel', event => {if (saving) event.preventDefault();});
    const close = view.dialog.querySelector('.apw-heading button');
    close?.addEventListener('click', event => {if (saving) {event.preventDefault(); event.stopImmediatePropagation();}}, true);
    chooser.addEventListener('change', () => {receipt = receipts.find(item => String(item.id) === chooser.value); draw();});
    view.foot.append(fill, cancel, validate); chooser.value = String(receipt.id); draw();
}
