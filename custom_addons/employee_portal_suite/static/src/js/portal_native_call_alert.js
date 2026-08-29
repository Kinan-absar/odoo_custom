/** @odoo-module **/

// Portal-wide alert for Odoo's *native* Discuss RTC invitation.
// It deliberately does not initialize WebRTC, join calls, or alter Discuss.
// The native public Discuss page remains the only RTC frontend.

const POLL_MS = 2500;
let timer = null;
let activeChannelId = 0;

function isEmployeePortalPage() {
    return window.location.pathname.startsWith('/my/employee') &&
        !window.location.pathname.startsWith('/my/employee/discuss/channel/');
}

async function jsonRpc(route, params = {}) {
    const response = await fetch(route, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({jsonrpc: '2.0', method: 'call', params, id: Date.now()}),
    });
    const payload = await response.json();
    if (payload.error) {
        throw new Error(payload.error.data?.message || payload.error.message || 'RPC error');
    }
    return payload.result;
}

function removeAlert() {
    document.getElementById('ep-native-call-alert')?.remove();
    activeChannelId = 0;
}

function showAlert(call) {
    if (!call?.channel_id) {
        removeAlert();
        return;
    }
    if (activeChannelId === call.channel_id && document.getElementById('ep-native-call-alert')) {
        return;
    }
    removeAlert();
    activeChannelId = call.channel_id;
    const root = document.createElement('div');
    root.id = 'ep-native-call-alert';
    root.className = 'ep-native-call-alert';
    const avatar = call.caller_avatar
        ? `<img class="ep-native-call-avatar" src="${call.caller_avatar}" alt="">`
        : `<div class="ep-native-call-avatar ep-native-call-avatar-fallback"><i class="fa fa-user"></i></div>`;
    root.innerHTML = `
        ${avatar}
        <div class="ep-native-call-copy">
            <strong></strong>
            <span>${call.is_video ? 'Incoming video call' : 'Incoming audio call'}</span>
        </div>
        <div class="ep-native-call-actions">
            <button type="button" class="ep-native-call-decline" aria-label="Decline"><i class="fa fa-phone"></i></button>
            <button type="button" class="ep-native-call-answer" aria-label="Answer"><i class="fa fa-phone"></i><span>Answer</span></button>
        </div>`;
    root.querySelector('strong').textContent = call.caller_name || call.channel_name || 'Incoming call';
    root.querySelector('.ep-native-call-answer').addEventListener('click', () => {
        window.location.assign(call.open_url);
    });
    root.querySelector('.ep-native-call-decline').addEventListener('click', async () => {
        try {
            await jsonRpc('/employee_portal/discuss/call/decline', {channel_id: call.channel_id});
        } finally {
            removeAlert();
        }
    });
    document.body.appendChild(root);
}

async function poll() {
    if (!isEmployeePortalPage() || document.hidden) {
        return;
    }
    try {
        const result = await jsonRpc('/employee_portal/discuss/call/poll');
        if (result?.call) {
            showAlert(result.call);
        } else {
            removeAlert();
        }
    } catch (_) {
        // Never let an optional alert interfere with the employee portal.
    }
}

function start() {
    if (!isEmployeePortalPage() || timer) {
        return;
    }
    poll();
    timer = window.setInterval(poll, POLL_MS);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) poll();
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
} else {
    start();
}
