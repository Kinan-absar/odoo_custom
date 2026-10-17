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
