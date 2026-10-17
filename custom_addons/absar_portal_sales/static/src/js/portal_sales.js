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
