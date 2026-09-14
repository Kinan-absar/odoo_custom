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
