/* Preserve EPS header tools and MR composer behavior when the shared bell
   replaces the old MR-only bell. EPS itself and its permissions stay unchanged. */
(function () {
    'use strict';
    function connectExistingCaller() {
        const caller = window.__employeePortalCaller;
        if (!caller || typeof caller._addPortalHeaderButton !== 'function') return;
        // Reuse the already-authorized EPS widget, never create another caller.
        document.querySelectorAll('[data-pbw-bell]').forEach(bell => {
            caller._addPortalHeaderButton(bell);
        });
    }
    function start() {
        if (!document.querySelector('[data-pbw-bell]')) return;
        document.querySelectorAll('.eps-mr-composer').forEach(form => {
            if (form.dataset.pbwSubmitGuard === '1') return;
            form.dataset.pbwSubmitGuard = '1';
            form.addEventListener('submit', () => {
                const button = form.querySelector('button[type="submit"]');
                if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
            });
        });
        connectExistingCaller();
        // EPS initializes its caller in a DOMContentLoaded handler. Defer once
        // so its handler can finish regardless of asset-listener registration order.
        window.setTimeout(connectExistingCaller, 0);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
    window.addEventListener('load', connectExistingCaller, {once: true});
}());
