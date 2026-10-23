/** @odoo-module **/
/* Identical portal line-list contract in Purchase, Sales and Accounting. */
const widths = new Map();
const gridListeners = new WeakMap();
export function isEmptyDraftLine(row) {
    if(!row)return true;
    const taxes=row.taxes_id||[];
    const onlyDefaultTaxes=!row._manualTaxes && Array.isArray(row._defaultTaxes) && JSON.stringify([...taxes].sort())===JSON.stringify([...row._defaultTaxes].sort());
    return !row.id && !row.display_type && !row.product_id && !row.account_id && !String(row.name || '').trim()
        && !Number(row.price_unit || 0) && !Number(row.debit || 0) && !Number(row.credit || 0)
        && !Number(row.discount || 0) && (!taxes.length || onlyDefaultTaxes) && !(row.tax_tag_ids || []).length
        && !row.partner_id && !row.product_uom_id && !row.uom_id && !row.product_uom
        && !Number(row.amount_currency || 0) && !Object.keys(row.analytic_distribution || {}).length
        && [0, 1].includes(Number(row.quantity ?? row.product_qty ?? 1));
}
export function calculationRows(lines) { return lines.filter(row => !isEmptyDraftLine(row)); }
export function decorateLineGrid(table, {editor, editable, entrySelector, onAppend, onReorder} = {}) {
    table.classList.add('absar-document-lines');
    table.dataset.lineEditor=editor;
    for(const row of table.querySelectorAll('tbody tr')){
        const description=row.querySelector('.apw-description,.aps-sales-description,.aca-line-description');
        const product=row.querySelector('input');
        if(description){
            description.classList.add('absar-line-description');
            const refresh=()=>{description.dataset.duplicate=String(!description.value.trim() || description.value.trim()===(product?.value||'').trim());};
            refresh();description.addEventListener('input',refresh);
        }
        for(const control of row.querySelectorAll('input'))if(control.value)control.title=control.value;
    }
    table.querySelectorAll('.absar-column-resize').forEach(node=>node.remove());
    const headers = [...table.querySelectorAll('thead th')];
    const saved = widths.get(editor);
    if (saved?.length === headers.length) {headers.forEach((cell, i) => cell.style.width = saved[i] + 'px');table.style.width = saved.reduce((a,b)=>a+b,0)+'px';}
    headers.forEach((header, index) => {
        if (index === headers.length - 1) return;
        const grip = document.createElement('span');grip.className = 'absar-column-resize';grip.title = 'Drag to resize column';
        grip.addEventListener('pointerdown', event => {
            event.preventDefault();event.stopPropagation();
            const sizes = headers.map(cell => cell.getBoundingClientRect().width), start = event.clientX;
            const move = e => {sizes[index]=Math.max(60,sizes[index]+e.clientX-(move.last??start));move.last=e.clientX;headers.forEach((cell,i)=>cell.style.width=sizes[i]+'px');table.style.width=sizes.reduce((a,b)=>a+b,0)+'px';widths.set(editor,[...sizes]);};
            const up = () => {window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',up);};
            window.addEventListener('pointermove',move);window.addEventListener('pointerup',up);
        });header.append(grip);
    });
    if (!editable) return;
    const prior=gridListeners.get(table);if(prior)table.removeEventListener('keydown',prior);
    const keydown = event => {
        if (event.key !== 'Tab' || event.defaultPrevented || event.isComposing || event.target.closest('.apw-options,.aca-options')) return;
        const currentCell = event.target.closest('td');if (!currentCell) return;
        const entries = [...table.querySelectorAll(entrySelector)].filter(node => !node.disabled);
        const current = entries.find(node => node.closest('td') === currentCell), index = entries.indexOf(current);
        if (index < 0) return;
        const next = entries[index + (event.shiftKey ? -1 : 1)];
        if (next) {event.preventDefault();next.focus();next.select?.();next.scrollIntoView?.({block:'nearest',inline:'nearest'});}
        else if (!event.shiftKey && onAppend && onAppend()!==false) event.preventDefault();
    };
    table.addEventListener('keydown',keydown);gridListeners.set(table,keydown);
    if (onReorder) [...table.querySelectorAll('tbody tr')].forEach((row, index) => {
        const tools = row.querySelector('.apw-row-actions,.aps-sales-tools,.aca-row-actions');if (!tools) return;
        const handle = document.createElement('span');handle.className='absar-row-grip';handle.textContent='⠿';handle.draggable=true;handle.title='Drag to reorder line';
        handle.addEventListener('dragstart',event=>{event.dataTransfer.setData('application/x-absar-line',String(index));event.dataTransfer.effectAllowed='move';});row.querySelector('td').append(handle);
        row.addEventListener('dragover',event=>{if([...event.dataTransfer.types].includes('application/x-absar-line'))event.preventDefault();});
        row.addEventListener('drop',event=>{const raw=event.dataTransfer.getData('application/x-absar-line');if(raw==='')return;event.preventDefault();const from=Number(raw);if(Number.isInteger(from)&&from!==index)onReorder(from,index);});
    });
}
