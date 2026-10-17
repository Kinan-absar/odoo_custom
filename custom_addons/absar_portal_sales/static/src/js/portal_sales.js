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
// Make each row navigable without interfering with regular links.
document.querySelectorAll('.aps-click-row').forEach(row => {
  const open = () => { if (row.dataset.href) window.location.assign(row.dataset.href); };
  row.addEventListener('click', e => { if (!e.target.closest('a, button, form, input')) open(); });
  row.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target === row) open(); });
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
// Only drag the handle (not the whole form with editable text fields).
document.querySelectorAll('.aps-sortable').forEach(list => {
  let dragged = null;
  let originalOrder = null;
  const sections = () => Array.from(list.querySelectorAll('.aps-section[data-section-id]'));
  const clear = () => {
    sections().forEach(s => s.classList.remove('aps-dragging','aps-drop-target'));
    dragged = null;
    originalOrder = null;
  };
  const submitOrder = () => {
    if (!dragged) return;
    const order = sections().map(s => s.dataset.sectionId);
    if (order.join(',') === originalOrder) { clear(); return; }
    const form = document.createElement('form');
    form.method = 'POST'; form.action = list.dataset.reorderUrl;
    [['csrf_token', list.dataset.csrf], ['section_ids', order.join(',')]].forEach(([name,value]) => {
      const input = document.createElement('input'); input.type='hidden'; input.name=name; input.value=value;
      form.appendChild(input);
    });
    document.body.appendChild(form);
    form.submit();
  };
  sections().forEach(section => {
    const handle = section.querySelector('.aps-drag-handle');
    if (!handle) return;
    handle.draggable = true;
    handle.addEventListener('dragstart', event => {
      dragged = section;
      originalOrder = sections().map(s => s.dataset.sectionId).join(',');
      section.classList.add('aps-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', section.dataset.sectionId);
    });
    section.addEventListener('dragover', event => {
      if (!dragged || dragged === section) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      const bounds = section.getBoundingClientRect();
      list.insertBefore(dragged, event.clientY < bounds.top + bounds.height / 2 ? section : section.nextSibling);
      section.classList.add('aps-drop-target');
    });
    section.addEventListener('dragleave', () => section.classList.remove('aps-drop-target'));
    section.addEventListener('drop', event => {
      if (!dragged) return;
      event.preventDefault(); event.stopPropagation();
      submitOrder();
    });
    handle.addEventListener('dragend', clear);
  });
  list.addEventListener('dragover', event => { if (dragged) event.preventDefault(); });
  list.addEventListener('drop', event => {
    if (!dragged) return;
    event.preventDefault();
    submitOrder();
  });
});
