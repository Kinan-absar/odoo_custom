/** @odoo-module **/
/** Scoped portal controls: no backend RPC or generic model access. */
let purchaseControlId = 0;
export function positionPurchaseOptions(rect, viewportWidth, viewportHeight) {
    const width = Math.min(Math.max(rect.width, 280), viewportWidth - 16);
    const below = viewportHeight - rect.bottom - 8, above = rect.top - 8;
    const down = below >= 180 || below >= above;
    const height = Math.max(48, Math.min(280, down ? below : above));
    return {left: Math.max(8, Math.min(rect.left, viewportWidth - width - 8)),
        top: Math.max(8, down ? rect.bottom + 2 : rect.top - height - 2), width, height};
}
export function createPurchaseUI({root, post, companyId, readonly = false}) {
    const text = (tag, value, className = '') => {
        const node = document.createElement(tag); node.textContent = value ?? ''; node.className = className; return node;
    };
    const button = (label, callback, cls = 'btn btn-light') => {
        const node = text('button', label, cls); node.type = 'button'; node.addEventListener('click', callback); return node;
    };
    const input = (value, type, onChange) => {
        const node = document.createElement('input'); node.className = 'form-control'; node.type = type || 'text'; node.value = value ?? '';
        if (type === 'number') node.step = 'any';
        let last = node.value;
        const commit = () => {if (node.value !== last) {last = node.value; onChange(node.value);}};
        node.addEventListener('input', commit); node.addEventListener('change', commit); return node;
    };
    const field = (label, node, host, hint = '') => {
        const wrap = text('div', '', 'apw-form-field'), labelNode = text('label', label);
        const control = node.matches?.('input, select, textarea') ? node : node.querySelector?.('input');
        if (control) {control.id ||= 'apw-control-' + (++purchaseControlId); labelNode.htmlFor = control.id;}
        wrap.append(labelNode, node);
        if (hint) wrap.append(text('small', hint, 'apw-help')); host.append(wrap); return node;
    };
    const modal = title => {
        const dialog = document.createElement('dialog'); dialog.className = 'apw-dialog'; dialog.setAttribute('aria-label', title);
        const head = text('div', '', 'apw-heading'); head.append(text('h3', title), button('Close', () => dialog.close()));
        const body = text('div', '', 'apw-dialog-body'), foot = text('div', '', 'apw-actions'); dialog.append(head, body, foot);
        const focus = document.activeElement;
        dialog.addEventListener('close', () => {dialog.querySelectorAll('.apw-lookup').forEach(node => node.dispatchEvent(new Event('apw-dispose'))); dialog.remove(); if (focus?.isConnected) focus.focus();});
        root.append(dialog); dialog.showModal(); return {dialog, body, foot};
    };
    const searchMore = (kind, query, onSelect, extras = {}) => {
        const view = modal('Search ' + kind), search = input(query, 'search', () => {});
        const list = text('div', '', 'apw-search-results'), pager = text('div', '', 'apw-pager');
        let offset = 0, sequence = 0, timer;
        const choose = async item => {view.dialog.close(); await onSelect(item);};
        async function load() {
            const current = ++sequence; list.replaceChildren(text('p', 'Searching…'));
            try {
                const result = await post('/lookup', {kind, q: search.value, company_id: companyId, offset, ...extras});
                if (current !== sequence || !view.dialog.open) return;
                list.replaceChildren();
                for (const item of result.items) list.append(button(item.label, () => choose(item), 'apw-option'));
                if (!result.items.length) list.append(text('p', 'No matching records'));
                pager.replaceChildren();
                if (offset) pager.append(button('Previous', () => {offset = Math.max(0, offset - 30); load();}));
                pager.append(text('span', 'Page ' + (offset / 30 + 1)));
                if (result.more) pager.append(button('Next', () => {offset += 30; load();}));
            } catch (error) {list.replaceChildren(text('p', error.message));}
        }
        search.setAttribute('aria-label', 'Search records');
        search.addEventListener('input', () => {sequence++; clearTimeout(timer); timer = setTimeout(() => {offset = 0; load();}, 180);});
        view.dialog.addEventListener('close', () => {sequence++; clearTimeout(timer);});
        view.body.append(search, list); view.foot.append(pager); load(); search.focus();
    };
    const lookup = (kind, selected, onSelect, extras = {}, actions = {}) => {
        const wrap = text('div', '', 'apw-lookup'), box = input(selected?.label || '', 'search', () => {});
        const options = text('div', '', 'apw-options');
        box.placeholder = 'Search…'; box.autocomplete = 'off'; box.disabled = readonly;
        box.setAttribute('aria-label', kind + ' search'); box.setAttribute('role', 'combobox'); box.setAttribute('aria-expanded', 'false');
        options.hidden = true; options.setAttribute('popover', 'manual'); options.setAttribute('role', 'listbox');
        let selectedItem = selected?.id ? selected : null, timer, sequence = 0, listening = false, keyboardAdvance = false;
        const position = () => {
            if (!box.isConnected) {close(); return;}
            const rect = box.getBoundingClientRect();
            if (rect.bottom < 0 || rect.top > window.innerHeight) {close(); return;}
            const p = positionPurchaseOptions(rect, window.innerWidth, window.innerHeight);
            const height = Math.min(p.height, options.scrollHeight || p.height);
            const top = p.top < rect.top ? Math.max(8, rect.top - height - 2) : p.top;
            Object.assign(options.style, {left: p.left + 'px', top: top + 'px', width: p.width + 'px', maxHeight: p.height + 'px'});
        };
        const close = () => {
            sequence++; clearTimeout(timer);
            if (typeof options.hidePopover === 'function' && options.matches(':popover-open')) options.hidePopover();
            options.hidden = true; box.setAttribute('aria-expanded', 'false');
            if (listening) {window.removeEventListener('resize', position); window.removeEventListener('scroll', position, true); listening = false;}
        };
        const show = () => {
            position(); options.hidden = false;
            if (typeof options.showPopover === 'function' && !options.matches(':popover-open')) options.showPopover();
            box.setAttribute('aria-expanded', 'true');
            if (!listening) {window.addEventListener('resize', position); window.addEventListener('scroll', position, true); listening = true;}
        };
        const choose = async (item, advance = keyboardAdvance) => {
            keyboardAdvance = false; close(); selectedItem = item; box.value = item?.label || '';
            try {await onSelect(item); if (advance) actions.advance?.();}
            catch (error) {actions.onError?.(error);}
        };
        const option = (label, callback) => {
            const node = button(label, callback, 'apw-option'); node.setAttribute('role', 'option');
            node.addEventListener('pointerdown', event => event.preventDefault()); return node;
        };
        const editProduct = async (id, name = '') => {
            close(); try {await actions.productForm?.(id, name, item => choose(item));} catch (error) {actions.onError?.(error);}
        };
        const addActions = () => {
            options.append(option('Search More…', () => {close(); searchMore(kind, box.value, item => choose(item), extras);}));
            if (kind === 'product' && actions.productForm && !readonly) {
                options.append(option('Create and Edit…', () => editProduct(null, selectedItem ? '' : box.value)));
                if (selectedItem) options.append(option('Open / Edit Product', () => editProduct(selectedItem.id)));
            }
            options.append(option('Clear selection', () => choose(null)));
        };
        async function search() {
            if (readonly) return;
            const current = ++sequence; options.replaceChildren(text('div', 'Searching…', 'apw-help')); show();
            try {
                const result = await post('/lookup', {kind, q: selectedItem && box.value === selectedItem.label ? '' : box.value, company_id: companyId, ...extras});
                if (current !== sequence || !box.isConnected || options.hidden) return;
                options.replaceChildren();
                for (const item of result.items) {const node = option(item.label + (item.plan ? ' · ' + item.plan : ''), () => choose(item)); node.dataset.lookupRecord = '1'; options.append(node);}
                if (!result.items.length) options.append(text('div', 'No matches', 'apw-help'));
                addActions(); position();
            } catch (error) {if (current === sequence) options.replaceChildren(text('div', error.message, 'apw-help'));}
        }
        box.addEventListener('focus', () => {if (box.dataset.suppressLookupOnce) {delete box.dataset.suppressLookupOnce; return;} search();});
        box.addEventListener('input', () => {
            sequence++; if (selectedItem) {selectedItem = null; onSelect(null);}
            clearTimeout(timer); timer = setTimeout(search, 180);
        });
        box.addEventListener('keydown', event => {
            if (event.key === 'Escape') {event.preventDefault(); close(); return;}
            if (event.key === 'ArrowDown') {event.preventDefault(); options.querySelector('button')?.focus(); return;}
            if (event.key === 'Tab' && !event.shiftKey && !options.hidden && !selectedItem) {
                const first=options.querySelector('button[data-lookup-record="1"]');
                if(first){event.preventDefault();keyboardAdvance=true;first.click();return;}
            }
            if (event.key === 'Enter') {
                event.preventDefault();
                if (selectedItem && box.value === selectedItem.label) {close(); actions.advance?.();}
                else if (!options.hidden) {const first = options.querySelector('button[role="option"]'); if (first) {keyboardAdvance = first.dataset.lookupRecord === '1'; first.click();}}
                else search();
            }
        });
        options.addEventListener('keydown', event => {
            const nodes = [...options.querySelectorAll('button')], index = nodes.indexOf(document.activeElement);
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {event.preventDefault(); nodes[(index + (event.key === 'ArrowDown' ? 1 : -1) + nodes.length) % nodes.length]?.focus();}
            if (event.key === 'Escape') {event.preventDefault(); close(); box.dataset.suppressLookupOnce = '1'; box.focus();}
            if (event.key === 'Enter') {event.preventDefault(); event.stopPropagation(); keyboardAdvance = document.activeElement?.dataset.lookupRecord === '1'; document.activeElement?.click();}
        });
        wrap.addEventListener('focusout', () => setTimeout(() => {if (!wrap.contains(document.activeElement)) close();}, 100));
        wrap.addEventListener('apw-dispose', close);
        wrap.append(box, options);
        if (kind === 'product' && selectedItem && actions.productForm) {
            const open = button('↗', () => editProduct(selectedItem.id), 'apw-open-product'); open.title = 'Open product'; open.setAttribute('aria-label', 'Open product'); wrap.append(open);
        }
        return wrap;
    };
    return {text, button, input, field, modal, lookup, searchMore};
}
