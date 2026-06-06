/** @odoo-module **/

/**
 * After the user finishes signing, Odoo's sign widget navigates to
 * /my/signatures (the portal signatures list). We intercept that
 * navigation and send employees to /my/employee/sign instead.
 *
 * Strategy: patch window.location assignment via history.pushState
 * and a beforeunload-style check, PLUS directly intercept the Close
 * button in the "It's signed!" dialog.
 */

(function () {
    if (!window.location.pathname.startsWith('/sign/document/')) {
        return;
    }

    // -- Strategy 1: intercept the Close button directly --
    function patchDialog(root) {
        const buttons = root.querySelectorAll('button');
        buttons.forEach(function (btn) {
            const txt = btn.textContent.trim();
            // Match "Close" in any language by also checking aria or class,
            // but text is reliable from the screenshot
            if (!btn.dataset.epPatched) {
                btn.dataset.epPatched = '1';
                btn.addEventListener('click', function (e) {
                    // Give Odoo's handler a tick to run, then override location
                    setTimeout(function () {
                        if (window.location.pathname.startsWith('/my/signature')) {
                            window.location.replace('/my/employee/sign');
                        }
                    }, 0);
                }, true); // capture phase so we run before Odoo's handler
            }
        });
    }

    // -- Strategy 2: intercept window.location changes directly --
    // Override location.assign and location.replace
    const origAssign   = window.location.assign.bind(window.location);
    const origReplace  = window.location.replace.bind(window.location);

    window.location.assign = function (url) {
        if (typeof url === 'string' && url.includes('/my/signature')) {
            origAssign('/my/employee/sign');
        } else {
            origAssign(url);
        }
    };

    window.location.replace = function (url) {
        if (typeof url === 'string' && url.includes('/my/signature')) {
            origReplace('/my/employee/sign');
        } else {
            origReplace(url);
        }
    };

    // Override history.pushState / replaceState too
    const origPush    = history.pushState.bind(history);
    const origReplaceS = history.replaceState.bind(history);

    history.pushState = function (state, title, url) {
        if (typeof url === 'string' && url.includes('/my/signature')) {
            return origPush(state, title, '/my/employee/sign');
        }
        return origPush(state, title, url);
    };

    history.replaceState = function (state, title, url) {
        if (typeof url === 'string' && url.includes('/my/signature')) {
            return origReplaceS(state, title, '/my/employee/sign');
        }
        return origReplaceS(state, title, url);
    };

    // -- Strategy 3: MutationObserver watches for the dialog --
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
            m.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                patchDialog(node);
                const children = node.querySelectorAll('*');
                children.forEach(function (c) { patchDialog(c); });
            });
        });
    });

    document.addEventListener('DOMContentLoaded', function () {
        observer.observe(document.body, { childList: true, subtree: true });
        // Patch anything already in the DOM
        patchDialog(document.body);
    });

    // Also run immediately in case DOM is already ready
    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    }
})();
