/** @odoo-module **/

/**
 * Intercepts the post-signing redirect in Odoo 18's sign widget.
 *
 * After the user signs, the OWL ThankYouDialog closes and the JS sets
 * window.location to /my/signature/<id>. We patch window.location via
 * a MutationObserver + event delegation on the Close button so that
 * employees are sent to /my/employee/sign instead.
 *
 * This runs only on /sign/document/* pages.
 */

(function () {
    // Only activate on the sign document portal page
    if (!window.location.pathname.startsWith('/sign/document/')) {
        return;
    }

    /**
     * When the "It's signed!" dialog appears, rewrite the Close button
     * so it sends the user to /my/employee/sign instead of /my/signature.
     */
    function patchCloseButton(dialog) {
        // The Close button is any button whose text is exactly "Close"
        // (Odoo uses _t("Close") — English default shown in screenshot)
        const buttons = dialog.querySelectorAll('button');
        buttons.forEach(function (btn) {
            const label = btn.textContent.trim();
            if (label === 'Close' || label === 'إغلاق') {
                // Clone to strip existing listeners, then re-add ours
                const fresh = btn.cloneNode(true);
                btn.parentNode.replaceChild(fresh, btn);
                fresh.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    window.location.href = '/my/employee/sign';
                });
            }
        });
    }

    // Watch for the dialog being injected into the DOM
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;

                // The dialog contains the text "It's signed!" or similar
                // Odoo renders it inside a .modal or an OWL dialog wrapper
                const text = node.textContent || '';
                if (text.includes("It's signed") || text.includes("signed")) {
                    patchCloseButton(node);
                }

                // Also search descendants
                const dialogs = node.querySelectorAll
                    ? node.querySelectorAll('.o_dialog, .modal-dialog, [role="dialog"]')
                    : [];
                dialogs.forEach(patchCloseButton);
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });
})();
