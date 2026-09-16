/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

function setBadge(count) {
    const value = Math.max(0, Number(count || 0));
    document.querySelectorAll(".ep-native-unread-badge").forEach((badge) => {
        badge.textContent = value > 99 ? "99+" : String(value);
        badge.style.display = value ? "inline-flex" : "none";
    });
    try { sessionStorage.setItem("ep_discuss_unread_total", String(value)); } catch (_) {}
}

function renderRowCounts(counts = {}) {
    document.querySelectorAll("[data-ep-thread][data-channel-id]").forEach((row) => {
        const count = Math.max(0, Number(counts[String(row.dataset.channelId)] || 0));
        let badge = row.querySelector("[data-ep-row-unread]");
        if (!count) { badge?.remove(); return; }
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "ep-chats-unread";
            badge.dataset.epRowUnread = "1";
            row.appendChild(badge);
        }
        badge.textContent = count > 99 ? "99+" : String(count);
    });
}

async function refreshUnread({ force = false } = {}) {
    const hasPortalBadge = Boolean(document.querySelector(".ep-native-message-btn"));
    const hasThreadRows = Boolean(document.querySelector("[data-ep-thread][data-channel-id]"));
    if (!force && !hasPortalBadge && !hasThreadRows) return;
    try {
        const result = await rpc("/employee_portal/discuss/unread", {});
        setBadge(result?.unread || 0);
        renderRowCounts(result?.channels || {});
    } catch (_) {
        // Communication badges must never interfere with the portal page.
    }
}

function refreshSoon() {
    window.setTimeout(() => refreshUnread({ force: true }), 80);
}

document.addEventListener("DOMContentLoaded", () => {
    // If the browser restored the portal from BFCache, clear stale visual state
    // immediately using the total saved by the Chats page, then confirm with Odoo.
    try {
        const cached = sessionStorage.getItem("ep_discuss_unread_total");
        if (cached !== null) setBadge(Number(cached || 0));
    } catch (_) {}
    refreshUnread({ force: true });
    window.setInterval(() => refreshUnread(), 5000);
});

window.addEventListener("pageshow", refreshSoon);
window.addEventListener("focus", refreshSoon);
document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshSoon();
});
