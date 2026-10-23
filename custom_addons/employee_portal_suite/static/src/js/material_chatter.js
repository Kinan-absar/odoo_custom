/* The portal bell reads the same unread MR inbox rows as Odoo's backend. */
(function () {
    'use strict';
    let inFlight = false;
    function renderCount(count) {
        document.querySelectorAll('.ep-bell-wrap').forEach(wrap => {
            const panel = wrap.querySelector('.ep-bell-panel');
            const button = wrap.querySelector('.ep-bell-btn');
            if (!panel || !button) return;
            let row = panel.querySelector('[data-eps-notification-kind="mr_message"]');
            if (count && !row) {
                row = document.createElement('a');
                row.href = '/my/employee/material/notifications';
                row.className = 'ep-bell-item';
                row.dataset.epsNotificationKind = 'mr_message';
                const icon = document.createElement('div');
                icon.className = 'ep-bell-item-icon';
                const glyph = document.createElement('i'); glyph.className = 'fa fa-comments-o';
                icon.appendChild(glyph); row.appendChild(icon);
                const label = document.createElement('span'); label.className = 'ep-bell-item-label';
                label.textContent = 'Material Request messages'; row.appendChild(label);
                const counter = document.createElement('span'); counter.className = 'ep-bell-item-count';
                row.appendChild(counter); panel.appendChild(row);
            }
            if (row && count) row.querySelector('.ep-bell-item-count').textContent = count + ' new';
            if (row && !count) row.remove();
            const total = count + Number(wrap.dataset.epsOtherUnread || 0);
            button.classList.toggle('has-unread', total > 0);
            let dot = button.querySelector('.ep-bell-dot');
            if (total && !dot) { dot = document.createElement('span'); dot.className = 'ep-bell-dot'; button.appendChild(dot); }
            if (!total && dot) dot.remove();
            let empty = panel.querySelector('.ep-bell-empty');
            if (total && empty) empty.remove();
            if (!total && !empty) { empty = document.createElement('div'); empty.className = 'ep-bell-empty'; empty.textContent = "You're all caught up."; panel.appendChild(empty); }
        });
    }
    async function refresh() {
        if (inFlight || document.hidden || !document.querySelector('.ep-bell-wrap')) return;
        inFlight = true;
        try {
            const response = await fetch('/my/employee/material/notifications/summary', {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({jsonrpc: '2.0', method: 'call', params: {}, id: Date.now()}),
            });
            if (!response.ok) return;
            const payload = await response.json();
            if (payload.result && Number.isInteger(payload.result.count) && payload.result.count >= 0) renderCount(payload.result.count);
        } catch (_) { /* Keep the last known badge when offline. */ }
        finally { inFlight = false; }
    }
    function init() {
        if (!document.querySelector('.ep-bell-wrap')) return;
        refresh(); setInterval(refresh, 20000);
        document.addEventListener('visibilitychange', refresh);
        window.addEventListener('focus', refresh);
        document.addEventListener('click', event => { if (event.target.closest('.ep-bell-btn')) refresh(); });
        document.querySelectorAll('.eps-mr-composer').forEach(form => {
            form.addEventListener('submit', () => {
                const button = form.querySelector('button[type="submit"]');
                if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
            });
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
    if (typeof module !== 'undefined') module.exports = {renderCount};
}());
