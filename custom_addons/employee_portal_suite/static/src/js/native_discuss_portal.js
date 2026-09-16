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
        const counts = result?.channels || {};
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
    } catch (_) {
        // Communication badge must never interfere with the portal page.
    }
}

document.addEventListener("DOMContentLoaded", () => {
    refreshUnread();
    window.setInterval(refreshUnread, 5000);
});
