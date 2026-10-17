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
// Native HTML drag/reorder: post only a complete ordered set of section IDs.
document.querySelectorAll('.aps-sortable').forEach(list => {
  let dragged = null;
  list.querySelectorAll('.aps-section[draggable="true"]').forEach(section => {
    section.addEventListener('dragstart', event => {
      if (!event.target.closest('.aps-drag-handle')) { event.preventDefault(); return; }
      dragged = section; section.classList.add('aps-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', section.dataset.sectionId);
    });
    section.addEventListener('dragover', event => {
      if (!dragged || dragged === section) return;
      event.preventDefault();
      const middle = section.getBoundingClientRect().top + section.offsetHeight / 2;
      list.insertBefore(dragged, event.clientY < middle ? section : section.nextSibling);
    });
    section.addEventListener('drop', event => {
      event.preventDefault(); if (!dragged) return;
      const values = [...list.querySelectorAll('.aps-section')].map(s => s.dataset.sectionId);
      const form = document.createElement('form'); form.method = 'POST'; form.action = list.dataset.reorderUrl;
      [['csrf_token',list.dataset.csrf],['section_ids',values.join(',')]].forEach(([key,val]) => {
        const field = document.createElement('input'); field.type = 'hidden'; field.name = key; field.value = val; form.appendChild(field);
      });
      document.body.appendChild(form); form.submit();
    });
    section.addEventListener('dragend', () => { section.classList.remove('aps-dragging'); dragged = null; });
  });
});
