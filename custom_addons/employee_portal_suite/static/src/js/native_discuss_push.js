(() => {
    if (window.__employeeChatsPushLoaded) return;
    window.__employeeChatsPushLoaded = true;
    console.info("[Chats Push] notification client loaded");
    const APP_ROOT = "/my/employee";
    const DISCUSS_ROOT = "/my/employee/discuss";
    if (!window.location.pathname.startsWith(DISCUSS_ROOT)) return;

    const buttonSelector = "[data-ep-push-toggle]";
    let vapidPublicKey = null;
    let busy = false;

    function b64ToUint8Array(value) {
        const padding = "=".repeat((4 - value.length % 4) % 4);
        const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
        const raw = window.atob(base64);
        return Uint8Array.from(raw, (char) => char.charCodeAt(0));
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            cache: "no-store",
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) {
            throw new Error(data.error || `Request failed (${response.status})`);
        }
        return data;
    }

    function standaloneMode() {
        return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    }

    function isIOS() {
        return /iphone|ipad|ipod/i.test(navigator.userAgent || "") ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    }

    function setState(state, title) {
        document.querySelectorAll(buttonSelector).forEach((button) => {
            button.dataset.pushState = state;
            button.disabled = busy || state === "unsupported";
            button.classList.toggle("ep-push-enabled", state === "on");
            button.title = title || (state === "on" ? "Notifications enabled" : "Enable notifications");
            button.setAttribute("aria-label", button.title);
            const label = button.querySelector("[data-ep-push-label]");
            if (label) label.textContent = state === "on" ? "Notifications on" : "Notifications";
        });
    }

    async function getRegistration() {
        if (!("serviceWorker" in navigator)) throw new Error("Service workers are not supported on this device.");
        if (!window.isSecureContext) throw new Error("Notifications require HTTPS / a secure connection.");
        const registration = await navigator.serviceWorker.register(`${APP_ROOT}/sw.js`, { scope: APP_ROOT });
        try { await registration.update(); } catch (_) {}
        await navigator.serviceWorker.ready;
        return registration;
    }

    async function syncExistingSubscription() {
        if (!("Notification" in window) || !("PushManager" in window)) {
            setState("unsupported", "Push notifications are not supported in this browser.");
            return;
        }
        const config = await api("/employee_portal/push/config");
        vapidPublicKey = config.public_key;
        const registration = await getRegistration();
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
            await api("/employee_portal/push/subscribe", {
                method: "POST",
                body: JSON.stringify({ subscription: subscription.toJSON() }),
            });
            setState("on");
        } else {
            setState("off");
        }
    }

    async function enableNotifications() {
        if (!("Notification" in window) || !("PushManager" in window)) {
            throw new Error("Push notifications are not supported in this browser.");
        }
        if (isIOS() && !standaloneMode()) {
            throw new Error("On iPhone/iPad, install the Employee Portal on the Home Screen first, then enable notifications from the installed app.");
        }
        if (Notification.permission === "denied") {
            throw new Error("Notifications are blocked for the Employee Portal. Enable them in your browser/device settings first.");
        }
        const permission = Notification.permission === "granted"
            ? "granted"
            : await Notification.requestPermission();
        if (permission !== "granted") {
            throw new Error("Notification permission was not granted.");
        }
        if (!vapidPublicKey) {
            const config = await api("/employee_portal/push/config");
            vapidPublicKey = config.public_key;
        }
        const registration = await getRegistration();
        // Prove that this browser/PWA can actually display a notification before
        // involving the server-side Web Push delivery path.
        try {
            await registration.showNotification("ABSAR Employee", {
                body: "Notifications are enabled on this device.",
                icon: "/employee_portal_suite/static/icons/portal-192.png",
                badge: "/employee_portal_suite/static/icons/portal-64.png",
                tag: "employee-chats-local-check",
                data: { url: DISCUSS_ROOT, kind: "test" },
            });
        } catch (error) {
            console.warn("[Chats Push] local notification check failed", error);
        }
        let subscription = await registration.pushManager.getSubscription();
        if (!subscription) {
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: b64ToUint8Array(vapidPublicKey),
            });
        }
        await api("/employee_portal/push/subscribe", {
            method: "POST",
            body: JSON.stringify({ subscription: subscription.toJSON() }),
        });
        setState("on");
        const test = await api("/employee_portal/push/test", { method: "POST", body: "{}" });
        if (!test.delivered) {
            throw new Error("The device subscribed, but Odoo could not deliver the server test push. Check the Odoo log for 'Web Push' delivery details.");
        }
        window.alert("Employee Portal notifications are enabled. A test notification was sent to this device.");
    }

    async function disableNotifications() {
        const registration = await getRegistration();
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) {
            await api("/employee_portal/push/unsubscribe", {
                method: "POST",
                body: JSON.stringify({ endpoint: subscription.endpoint }),
            });
            await subscription.unsubscribe();
        }
        setState("off");
    }

    async function toggleNotifications(event) {
        const button = event.target.closest?.(buttonSelector);
        if (!button || busy) return;
        event.preventDefault();
        event.stopPropagation();
        busy = true;
        const previousState = button.dataset.pushState || "off";
        document.querySelectorAll(buttonSelector).forEach((item) => {
            const label = item.querySelector("[data-ep-push-label]");
            if (label) label.textContent = previousState === "on" ? "Turning off…" : "Enabling…";
            item.disabled = true;
        });
        try {
            if (previousState === "on") {
                await disableNotifications();
            } else {
                await enableNotifications();
            }
        } catch (error) {
            console.error("Chats push notification setup failed", error);
            window.alert(error.message || "Unable to configure notifications.");
            try { await syncExistingSubscription(); } catch (_) {}
        } finally {
            busy = false;
            document.querySelectorAll(buttonSelector).forEach((item) => { item.disabled = false; });
        }
    }

    window.EmployeeChatsPush = {
        enable: enableNotifications,
        disable: disableNotifications,
        sync: syncExistingSubscription,
        toggle: toggleNotifications,
    };
    document.addEventListener("click", toggleNotifications, true);
    const boot = () => syncExistingSubscription().catch((error) => {
        console.warn("Chats push status could not be loaded", error);
        setState("off");
    });
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot, { once: true });
    } else {
        boot();
    }
})();
