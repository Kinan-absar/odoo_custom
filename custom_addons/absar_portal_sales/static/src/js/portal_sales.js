/** @odoo-module **/
// In-page confirmations, without browser confirm() popups.
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('aps-modal');
  if (!modal) return;
  const label = document.getElementById('aps-modal-text');
  const ok = document.getElementById('aps-modal-ok');
  const cancel = document.getElementById('aps-modal-cancel');
  let form = null;
  function close() { modal.hidden = true; form = null; }
  cancel.addEventListener('click', close);
  modal.addEventListener('click', e => { if (e.target === modal) close(); });
  document.querySelectorAll('[data-aps-confirm]').forEach(button => {
    button.addEventListener('click', e => {
      e.preventDefault();
      form = button.closest('form');
      label.textContent = button.getAttribute('data-aps-confirm') || 'Continue?';
      modal.hidden = false;
    });
  });
  ok.addEventListener('click', () => { if (form) { const selected = form; close(); selected.requestSubmit(); } });
});
document.addEventListener('DOMContentLoaded', () => {
// Make each row navigable without interfering with regular links.
// One click opens the quotation; the row also gets selected styling.
// Register after DOM load so the page rows exist when listeners are attached.
document.querySelectorAll('.aps-click-row[data-href]').forEach(row => {
  const open = () => {
    const href = row.getAttribute('data-href');
    if (!href) return;
    document.querySelectorAll('.aps-click-row.aps-row-selected').forEach(other => other.classList.remove('aps-row-selected'));
    row.classList.add('aps-row-selected');
    window.location.assign(href);
  };
  row.addEventListener('click', event => {
    if (event.target.closest('a, button, input, select, textarea, form')) return;
    open();
  });
  row.addEventListener('keydown', event => {
    if (event.target === row && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      open();
    }
  });
});
// Rich-text content is posted through the existing HTML field; Odoo sanitizes on write.
document.querySelectorAll('.aps-editor').forEach(editor => {
  const body = editor.querySelector('.aps-editor-body');
  const field = editor.querySelector('textarea[name="content"]');
  if (!body || !field || editor.dataset.editable !== '1') return;
  const sync = () => { field.value = body.innerHTML; };
  body.addEventListener('input', sync);
  const form = editor.closest('form');
  if (form) form.addEventListener('submit', sync);
  editor.querySelectorAll('[data-aps-format]').forEach(btn => btn.addEventListener('click', () => {
    body.focus(); document.execCommand(btn.dataset.apsFormat, false, null); sync();
  }));
  const size = editor.querySelector('.aps-font-size');
  if (size) size.addEventListener('change', () => {
    if (!size.value) return;
    body.focus(); document.execCommand('fontSize', false, size.value); sync();
    size.value = '';
  });
  sync();
});
// Inline item entry stays inside the table; Cancel collapses the editor.
document.querySelectorAll('.aps-cancel-add').forEach(button => {
  button.addEventListener('click', () => {
    const details = button.closest('details');
    if (details) details.open = false;
  });
});

});

// Compact inline BOQ editor: reveal exactly one editable row below the existing items.
document.addEventListener('DOMContentLoaded', () => {
  const openButton = document.querySelector('.aps-boq-add-link');
  const editRow = document.getElementById('aps-boq-edit-row');
  if (!openButton || !editRow) return;
  const cancel = editRow.querySelector('.aps-boq-cancel');
  const qty = editRow.querySelector('input[name="qty"]');
  const rate = editRow.querySelector('input[name="rate"]');
  const preview = editRow.querySelector('.aps-boq-preview-amount');
  const form = document.getElementById('aps-boq-new-form');
  const sync = () => {
    const amount = Number(qty?.value || 0) * Number(rate?.value || 0);
    if (preview) preview.textContent = Number.isFinite(amount) ? amount.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) : '0.00';
  };
  openButton.addEventListener('click', () => {
    editRow.hidden = false;
    openButton.setAttribute('aria-expanded', 'true');
    editRow.querySelector('textarea[name="description"]')?.focus();
  });
  cancel?.addEventListener('click', () => {
    editRow.hidden = true;
    openButton.setAttribute('aria-expanded', 'false');
    form?.reset();
    sync();
    openButton.focus();
  });
  qty?.addEventListener('input', sync);
  rate?.addEventListener('input', sync);
  sync();

  // Save using the existing authenticated Odoo route, without reloading the page.
  // If JavaScript is unavailable the original POST form still works normally.
  form?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity() || form.dataset.saving === '1') return;
    const save = editRow.querySelector('.aps-boq-save');
    const feedback = document.createElement('div');
    feedback.className = 'aps-boq-inline-error';
    feedback.setAttribute('role', 'alert');
    editRow.querySelectorAll('.aps-boq-inline-error').forEach(el => el.remove());
    form.dataset.saving = '1';
    if (save) save.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: {'X-APS-Inline': '1', 'Accept': 'application/json'},
        credentials: 'same-origin'
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'Unable to save item.');
      const row = document.createElement('tr');
      row.className = 'aps-boq-data-row';
      const desc = document.createElement('td');
      desc.className = 'aps-boq-description';
      const details = document.createElement('details');
      details.className = 'aps-line-details';
      const summary = document.createElement('summary');
      summary.textContent = result.description;
      details.appendChild(summary);
      desc.appendChild(details);
      row.appendChild(desc);
      const append = (value, className='') => {
        const cell = document.createElement('td');
        if (className) cell.className = className;
        cell.textContent = value;
        row.appendChild(cell);
      };
      const number = value => Number(value).toFixed(2);
      append(result.unit);
      append(number(result.qty), 'text-end');
      append(number(result.rate), 'text-end');
      append(number(result.subtotal), 'text-end');
      const removeCell = document.createElement('td');
      removeCell.className = 'aps-boq-remove';
      const removeForm = document.createElement('form');
      removeForm.method = 'post';
      removeForm.action = result.delete_url;
      const csrf = document.createElement('input');
      csrf.type = 'hidden'; csrf.name = 'csrf_token';
      csrf.value = form.querySelector('[name="csrf_token"]')?.value || '';
      removeForm.appendChild(csrf);
      const remove = document.createElement('button');
      remove.type = 'submit'; remove.className = 'aps-boq-delete';
      remove.title = 'Remove item'; remove.setAttribute('aria-label', 'Remove item');
      remove.textContent = '×';
      removeForm.appendChild(remove);
      removeCell.appendChild(removeForm);
      row.appendChild(removeCell);
      const linkRow = document.querySelector('.aps-boq-add-link-row');
      linkRow?.parentNode.insertBefore(row, linkRow);
      const total = document.querySelector('.aps-boq-total-value');
      if (total) total.textContent = Number(result.total).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) + ' ' + result.currency;
      form.reset(); sync();
      editRow.hidden = true;
      openButton.setAttribute('aria-expanded', 'false');
      openButton.focus();
    } catch (error) {
      feedback.textContent = error.message || 'Unable to save item. Please try again.';
      editRow.querySelector('td')?.appendChild(feedback);
    } finally {
      delete form.dataset.saving;
      if (save) save.disabled = false;
    }
  });
});

// Only show projects assigned to the selected quotation customer.
document.addEventListener('DOMContentLoaded', () => {
  const customer = document.querySelector('.aps-customer-select');
  const select = document.querySelector('.aps-project-select');
  if (!customer || !select) return;
  const refresh = () => {
    const customerId = customer.selectedOptions[0]?.dataset.commercialId || '';
    Array.from(select.options).forEach(option => {
      if (!option.value) return;
      const matches = Boolean(customerId) && option.dataset.customerId === customerId;
      option.hidden = !matches;
      option.disabled = !matches;
      if (!matches && option.selected) select.value = '';
    });
  };
  customer.addEventListener('change', refresh);
  refresh();
});
