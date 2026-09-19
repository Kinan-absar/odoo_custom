
function enforceEmployeePortalFavicon() {
    const head = document.head;
    if (!head) return;
    // Odoo's web.layout ships its own favicon. Safari can keep choosing that
    // first icon even when a later PNG is present, so remove competing favicons
    // only on the Employee Portal surface and install one stable, cache-busted set.
    head.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((link) => {
        if (link.dataset.employeePortalIcon !== "1") link.remove();
    });
    head.querySelectorAll('link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]').forEach((link) => {
        if (link.dataset.employeePortalTouchIcon !== "1") link.remove();
    });
    const touchIcons = [
        ["apple-touch-icon", "", "/employee_portal_suite/static/icons/apple-touch-icon.png?v=45"],
        ["apple-touch-icon", "180x180", "/employee_portal_suite/static/icons/portal-180.png?v=45"],
        ["apple-touch-icon-precomposed", "", "/employee_portal_suite/static/icons/apple-touch-icon-precomposed.png?v=45"],
    ];
    for (const [rel, sizes, href] of touchIcons) {
        const link = document.createElement("link");
        link.rel = rel;
        if (sizes) link.sizes = sizes;
        link.href = href;
        link.dataset.employeePortalTouchIcon = "1";
        head.appendChild(link);
    }
    const icons = [
        ["shortcut icon", "image/x-icon", "", "/employee_portal_suite/static/icons/portal-favicon-v45.ico?v=45"],
        ["icon", "image/png", "16x16", "/employee_portal_suite/static/icons/portal-16.png?v=45"],
        ["icon", "image/png", "32x32", "/employee_portal_suite/static/icons/portal-32.png?v=45"],
        ["icon", "image/png", "64x64", "/employee_portal_suite/static/icons/portal-64.png?v=45"],
    ];
    for (const [rel, type, sizes, href] of icons) {
        const link = document.createElement("link");
        link.rel = rel;
        link.type = type;
        if (sizes) link.sizes = sizes;
        link.href = href;
        link.dataset.employeePortalIcon = "1";
        head.appendChild(link);
    }
}

(() => {
    if (window.__employeePortalPwaLoaded) return;
    window.__employeePortalPwaLoaded = true;

    const PORTAL_ROOT = "/my/employee";
    const PORTAL_SW = `${PORTAL_ROOT}/sw.js`;
    const LEGACY_CHATS_SCOPE_SUFFIX = "/my/employee/discuss/";

    if (!window.location.pathname.startsWith(PORTAL_ROOT)) return;

    async function cleanupLegacyChatsWorker() {
        if (!("serviceWorker" in navigator)) return;
        try {
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (const registration of registrations) {
                if (!registration.scope.endsWith(LEGACY_CHATS_SCOPE_SUFFIX)) continue;
                try {
                    const subscription = await registration.pushManager?.getSubscription?.();
                    if (subscription) {
                        try {
                            await fetch("/employee_portal/push/unsubscribe", {
                                method: "POST",
                                credentials: "same-origin",
                                cache: "no-store",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ endpoint: subscription.endpoint }),
                            });
                        } catch (_) {}
                        try { await subscription.unsubscribe(); } catch (_) {}
                    }
                } catch (_) {}
                try { await registration.unregister(); } catch (_) {}
            }
        } catch (_) {}
    }

    async function registerPortalWorker() {
        if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
        await cleanupLegacyChatsWorker();
        try {
            const registration = await navigator.serviceWorker.register(PORTAL_SW, { scope: PORTAL_ROOT });
            try { await registration.update(); } catch (_) {}
        } catch (error) {
            console.warn("[Employee Portal PWA] service worker registration failed", error);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", registerPortalWorker, { once: true });
    } else {
        registerPortalWorker();
    }
})();

if (window.location.pathname.startsWith("/my/employee")) {
    enforceEmployeePortalFavicon();
    document.addEventListener("DOMContentLoaded", enforceEmployeePortalFavicon, { once: true });
}
