(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
        else fn();
    }

    async function jsonRpc(route, params) {
        const response = await fetch(route, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: params || {}, id: Date.now()}),
        });
        const data = await response.json();
        if (data.error) throw new Error(data.error.data && data.error.data.message || data.error.message || 'RPC error');
        return data.result;
    }

    ready(function () {
        const modal = document.getElementById('ac-new-modal');
        const openModal = function () {
            if (!modal) return;
            modal.classList.add('show');
            modal.setAttribute('aria-hidden', 'false');
            setTimeout(function () { document.getElementById('ac-people-search')?.focus(); }, 50);
        };
        const closeModal = function () {
            modal?.classList.remove('show');
            modal?.setAttribute('aria-hidden', 'true');
        };
        ['ac-new-chat-btn', 'ac-new-chat-link', 'ac-start-first'].forEach(function (id) {
            document.getElementById(id)?.addEventListener('click', openModal);
        });
        document.querySelectorAll('[data-close-modal="1"]').forEach(function (el) { el.addEventListener('click', closeModal); });
        document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closeModal(); });

        const threadSearch = document.getElementById('ac-thread-search');
        threadSearch?.addEventListener('input', function () {
            const q = (threadSearch.value || '').trim().toLowerCase();
            document.querySelectorAll('.ac-thread').forEach(function (row) {
                row.hidden = q && !(row.dataset.name || '').includes(q);
            });
        });

        const peopleSearch = document.getElementById('ac-people-search');
        peopleSearch?.addEventListener('input', function () {
            const q = (peopleSearch.value || '').trim().toLowerCase();
            document.querySelectorAll('.ac-person').forEach(function (row) {
                row.hidden = q && !(row.dataset.name || '').includes(q);
            });
        });

        // Preserve the already-working portal RTC invitation state while on the PWA hub.
        let activeCall = null;
        const alert = document.getElementById('ac-call-alert');
        const callName = document.getElementById('ac-call-name');
        const callType = document.getElementById('ac-call-type');
        const callAvatar = document.getElementById('ac-call-avatar');
        const answer = document.getElementById('ac-call-answer');
        const decline = document.getElementById('ac-call-decline');

        function hideCall() { activeCall = null; if (alert) alert.hidden = true; }
        function showCall(call) {
            if (!call || !call.channel_id || !alert) return;
            activeCall = call;
            callName.textContent = call.caller_name || call.channel_name || 'Incoming call';
            callType.textContent = call.is_video ? 'Incoming video call' : 'Incoming audio call';
            if (call.caller_avatar) {
                callAvatar.src = call.caller_avatar;
                callAvatar.style.display = '';
            } else {
                callAvatar.removeAttribute('src');
                callAvatar.style.display = 'none';
            }
            alert.hidden = false;
        }

        answer?.addEventListener('click', function () {
            if (!activeCall) return;
            const url = new URL('/chat/channel/' + activeCall.channel_id, window.location.origin);
            url.searchParams.set('auto_answer', '1');
            url.searchParams.set('auto_video', activeCall.is_video ? '1' : '0');
            window.location.assign(url.toString());
        });
        decline?.addEventListener('click', async function () {
            if (!activeCall) return;
            try { await jsonRpc('/employee_portal/discuss/call/decline', {channel_id: activeCall.channel_id}); }
            catch (_) {}
            hideCall();
        });

        async function pollCall() {
            if (document.visibilityState !== 'visible') return;
            try {
                const result = await jsonRpc('/employee_portal/discuss/call/poll', {});
                if (result && result.call) showCall(result.call);
                else if (activeCall) hideCall();
            } catch (_) {}
        }
        pollCall();
        window.setInterval(pollCall, 3000);
    });
})();
