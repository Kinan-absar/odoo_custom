/** @odoo-module **/

const POLL_URL = "/my/employee/notifications/poll";
const POLL_INTERVAL_MS = 10000;

function isEmployeePortal() {
    return window.location.pathname.startsWith("/my/employee");
}

function showToast(title, message) {
    let container = document.getElementById("eps-portal-notification-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "eps-portal-notification-container";
        container.style.cssText = [
            "position:fixed",
            "top:18px",
            "right:18px",
            "z-index:99999",
            "display:flex",
            "flex-direction:column",
            "gap:10px",
            "max-width:min(390px,calc(100vw - 36px))",
        ].join(";");
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.style.cssText = [
        "background:#fff",
        "border:1px solid rgba(0,0,0,.08)",
        "border-radius:14px",
        "box-shadow:0 14px 40px rgba(0,0,0,.18)",
        "padding:14px 16px",
        "font-family:inherit",
        "color:#111827",
        "opacity:0",
        "transform:translateY(-8px)",
        "transition:opacity .2s ease,transform .2s ease",
    ].join(";");
    toast.innerHTML = `<div style="font-weight:700;margin-bottom:4px"></div><div style="font-size:14px;color:#4b5563"></div>`;
    toast.children[0].textContent = title;
    toast.children[1].textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.style.opacity = "1";
        toast.style.transform = "translateY(0)";
    });
    window.setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-8px)";
        window.setTimeout(() => toast.remove(), 250);
    }, 7000);
}

async function showDeviceNotification(notification) {
    const args = {
        title: notification.title,
        message: notification.message,
    };

    // Official Odoo store app native bridge (when exposed by the WebView).
    try {
        const mobile = window.odoo && window.odoo.mobile;
        if (mobile && typeof mobile.showNotification === "function") {
            await mobile.showNotification(args);
            return true;
        }
        if (mobile && mobile.methods && typeof mobile.methods.showNotification === "function") {
            await mobile.methods.showNotification(args);
            return true;
        }
    } catch (error) {
        console.warn("Employee Portal native notification failed", error);
    }

    // Browser/PWA fallback.
    try {
        if ("Notification" in window && Notification.permission === "granted") {
            const systemNotification = new Notification(notification.title, {
                body: notification.message,
                icon: "/employee_portal_suite/static/description/icon.png",
                tag: `eps-portal-${notification.id}`,
            });
            systemNotification.onclick = () => {
                window.focus();
                window.location.href = notification.target_url || "/my/employee";
                systemNotification.close();
            };
            return true;
        }
    } catch (error) {
        console.warn("Employee Portal browser notification failed", error);
    }
    return false;
}

async function displayNotification(notification) {
    const displayedOnDevice = await showDeviceNotification(notification);
    if (!displayedOnDevice || !document.hidden) {
        showToast(notification.title, notification.message);
    }
    if (navigator.vibrate) {
        navigator.vibrate([120, 60, 120]);
    }
}

let polling = false;
async function pollNotifications() {
    if (polling || !isEmployeePortal()) {
        return;
    }
    polling = true;
    try {
        const response = await fetch(POLL_URL, {
            method: "GET",
            credentials: "same-origin",
            headers: { Accept: "application/json" },
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(`Polling failed with HTTP ${response.status}`);
        }
        const data = await response.json();
        for (const notification of data.notifications || []) {
            await displayNotification(notification);
        }
    } catch (error) {
        console.warn("Employee Portal notification polling failed", error);
    } finally {
        polling = false;
    }
}

async function requestNotificationPermission() {
    const status = document.getElementById("eps-notification-permission-status");
    try {
        if (!("Notification" in window)) {
            if (status) status.textContent = "Browser notifications are unavailable; the Odoo app native bridge will still be tested.";
            return;
        }
        const permission = await Notification.requestPermission();
        if (status) {
            status.textContent = permission === "granted"
                ? "Phone/browser notification permission is enabled."
                : `Notification permission: ${permission}.`;
        }
    } catch (error) {
        if (status) status.textContent = "Could not request notification permission.";
        console.warn(error);
    }
}

function initialize() {
    if (!isEmployeePortal()) return;
    const enableButton = document.getElementById("eps-enable-notifications");
    if (enableButton) {
        enableButton.addEventListener("click", requestNotificationPermission);
    }
    pollNotifications();
    window.setInterval(pollNotifications, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) pollNotifications();
    });
    window.addEventListener("focus", pollNotifications);
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
} else {
    initialize();
}
