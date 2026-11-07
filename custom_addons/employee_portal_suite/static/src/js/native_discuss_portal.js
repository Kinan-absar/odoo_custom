/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

function setBadge(count) {
    document.querySelectorAll(".ep-native-unread-badge").forEach((badge) => {
        const value = Math.max(0, Number(count || 0));
        badge.textContent = value > 99 ? "99+" : String(value);
        badge.style.display = value ? "inline-flex" : "none";
    });
}

async function refreshUnread() {
    if (!document.querySelector(".ep-native-message-btn")) return;
    try {
        const result = await rpc("/employee_portal/discuss/unread", {});
        setBadge(result?.unread || 0);
    } catch (_) {
        // Communication badge must never interfere with the portal page.
    }
}

function handleExternalUnread(value) {
    if (value === undefined || value === null) return;
    setBadge(value);
}

window.addEventListener("storage", (event) => {
    if (event.key !== "employee_portal_discuss_unread" || !event.newValue) return;
    try {
        const payload = JSON.parse(event.newValue);
        handleExternalUnread(payload?.unread);
    } catch (_) {}
});

try {
    if (window.BroadcastChannel) {
        const channel = new BroadcastChannel("employee_portal_discuss");
        channel.addEventListener("message", (event) => {
            if (event.data?.type === "unread") handleExternalUnread(event.data.unread);
        });
    }
} catch (_) {}

document.addEventListener("DOMContentLoaded", () => {
    refreshUnread();
    window.setInterval(refreshUnread, 5000);
});
