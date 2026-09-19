/** @odoo-module **/

import { registry } from "@web/core/registry";

let activeChannelId = 0;

function isEmployeePortalShell() {
    return window.location.pathname.startsWith("/my/employee") &&
        !window.location.pathname.startsWith("/my/employee/discuss/channel/");
}

async function jsonRpc(route, params = {}) {
    const response = await fetch(route, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", method: "call", params, id: Date.now() }),
    });
    const payload = await response.json();
    if (payload.error) throw new Error(payload.error.data?.message || payload.error.message || "RPC error");
    return payload.result;
}

function removeAlert() {
    document.getElementById("ep-native-call-alert")?.remove();
    activeChannelId = 0;
}


function positionAlert(root) {
    if (!root) return;
    const mobile = window.matchMedia("(max-width: 768px)").matches;
    let top = mobile ? 12 : 76;
    if (mobile) {
        const header = document.querySelector(".mobile-app-header:not([style*='display: none']), .ep-mobile-topbar");
        if (header) {
            const rect = header.getBoundingClientRect();
            top = Math.max(12, Math.round(rect.bottom + 10));
        }
    } else {
        const actions = document.querySelector(".ep-desktop-top-actions");
        if (actions) {
            const rect = actions.getBoundingClientRect();
            top = Math.max(76, Math.round(rect.bottom + 12));
        }
    }
    root.style.setProperty("--ep-native-call-top", `${top}px`);
}

function showAlert(call) {
    if (!isEmployeePortalShell() || !call?.channel_id) return;
    if (activeChannelId === call.channel_id && document.getElementById("ep-native-call-alert")) return;
    removeAlert();
    activeChannelId = call.channel_id;
    const root = document.createElement("div");
    root.id = "ep-native-call-alert";
    root.className = "ep-native-call-alert";
    root.innerHTML = `
        <div class="ep-native-call-avatar ep-native-call-avatar-fallback"><i class="fa fa-user"></i></div>
        <div class="ep-native-call-copy"><strong></strong><span>${call.is_video ? "Incoming video call" : "Incoming audio call"}</span></div>
        <div class="ep-native-call-actions">
            <button type="button" class="ep-native-call-decline" aria-label="Decline"><i class="fa fa-phone"></i></button>
            <button type="button" class="ep-native-call-answer" aria-label="Answer"><i class="fa fa-phone"></i><span>Answer</span></button>
        </div>`;
    root.querySelector("strong").textContent = call.caller_name || "Incoming call";
    if (call.caller_avatar) {
        const avatarWrap = root.querySelector(".ep-native-call-avatar");
        avatarWrap.innerHTML = "";
        const img = document.createElement("img");
        img.src = call.caller_avatar;
        img.alt = call.caller_name || "Caller";
        img.className = "ep-native-call-avatar-image";
        img.addEventListener("error", () => {
            avatarWrap.innerHTML = '<i class="fa fa-user"></i>';
        }, { once: true });
        avatarWrap.appendChild(img);
    }
    root.querySelector(".ep-native-call-answer").addEventListener("click", () => {
        const url = new URL(call.open_url, window.location.origin);
        url.searchParams.set("auto_answer", "1");
        url.searchParams.set("auto_video", call.is_video ? "1" : "0");
        removeAlert();
        window.location.assign(url.toString());
    });
    root.querySelector(".ep-native-call-decline").addEventListener("click", async () => {
        try { await jsonRpc("/employee_portal/discuss/call/decline", { channel_id: call.channel_id }); }
        finally { removeAlert(); }
    });
    document.body.appendChild(root);
    positionAlert(root);
    const reposition = () => positionAlert(root);
    window.addEventListener("resize", reposition, { passive: true });
    window.visualViewport?.addEventListener("resize", reposition, { passive: true });
}

const portalNativeCallAlertService = {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        if (!isEmployeePortalShell()) return;
        bus_service.subscribe("employee_portal.native_rtc_invitation", (payload) => showAlert(payload));
        // Recovery only: if the bus event arrived during navigation/reload, the
        // server's native invitation state can still restore the popup once.
        jsonRpc("/employee_portal/discuss/call/poll").then((r) => r?.call && showAlert(r.call)).catch(() => {});
    },
};

registry.category("services").add("employee_portal.native_call_alert", portalNativeCallAlertService);
