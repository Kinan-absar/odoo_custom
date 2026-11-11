/* Shared by the standalone workspace and the optional EPS bridge.
   A single singleton/poller reads the same server records in either interface. */
(function () {
    'use strict';
    if (window.PbwNotificationBell) return;
    const FEED = '/my/workspace/notifications/bell';
    const READ = '/my/workspace/notifications/read-json';
    const REFRESH_MS = 20000;
    const CHANGE_KEY = 'pbw.notification.read.changed';
    let started = false, timer = null, inFlight = false, reading = false;
    let lastRefresh = 0, sequence = 0, applied = 0, channel = null;
    let latest = null;
    const wraps = () => Array.from(document.querySelectorAll('[data-pbw-bell]'));
    const node = (tag, cls, text) => {
        const element = document.createElement(tag);
        if (cls) element.className = cls;
        if (text !== undefined) element.textContent = String(text);
        return element;
    };
    const number = value => Number.isSafeInteger(Number(value)) && Number(value) >= 0 ? Number(value) : 0;
    function safeURL(value) {
        if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\x00-\x20]/.test(value)) return null;
        try {
            const url = new URL(value, location.origin);
            return url.origin === location.origin && /^\/my\/(workspace|employee)(\/|$)/.test(url.pathname) ? url.pathname + url.search + url.hash : null;
        } catch (_) { return null; }
    }
    function announce(message) {
        wraps().forEach(wrap => {
            const target = wrap.querySelector('.pbw-notification-status');
            if (target) target.textContent = message || '';
        });
    }
    function apply(payload, ticket) {
        if (ticket < applied || !payload || payload.version !== 1 || !Array.isArray(payload.items)) return false;
        applied = ticket;
        latest = payload;
        const seen = new Set();
        const items = payload.items.filter(item => {
            if (!item || typeof item.key !== 'string' || seen.has(item.key) || !safeURL(item.url)) return false;
            seen.add(item.key);
            return true;
        });
        const total = number(payload.unread_count);
        wraps().forEach(wrap => {
            wrap.dataset.workspaceWatermark = String(number(payload.workspace_watermark));
            wrap.dataset.workspaceUnread = String(number(payload.workspace_unread_count));
            const trigger = wrap.querySelector('.pbw-notification-trigger');
            const badge = wrap.querySelector('.pbw-notification-badge');
            if (trigger) trigger.setAttribute('aria-label', 'Notifications: ' + total + ' unread');
            if (badge) { badge.textContent = total > 99 ? '99+' : String(total); badge.hidden = total === 0; }
            const label = wrap.querySelector('[data-pbw-bell-total]');
            if (label) label.textContent = total + ' unread';
            const contents = [];
            items.forEach(item => {
                const row = node('article', 'pbw-notification-row');
                row.dataset.notificationKey = item.key;
                const link = node('a', 'pbw-notification-link');
                link.href = safeURL(item.url);
                link.dataset.source = item.source;
                if (item.source === 'workspace' && number(item.id)) link.dataset.noticeId = String(number(item.id));
                const category = item.source === 'eps' ? 'Employee Portal' : ({sales:'Sales',purchase:'Purchase',accounting:'Accounting',hr:'HR'}[item.category] || 'Workspace');
                link.append(node('span', 'pbw-notification-source', category), node('strong', 'pbw-notification-title', item.title || 'Notification'));
                if (item.body) link.append(node('span', 'pbw-notification-body', item.body));
                if (item.source === 'eps') link.append(node('span', 'pbw-notification-count', number(item.count) + ' new'));
                if (item.date) {
                    const utcDate = new Date(String(item.date).replace(' ', 'T') + 'Z');
                    const time = node('time', 'pbw-notification-time', Number.isNaN(utcDate.valueOf()) ? item.date : utcDate.toLocaleString());
                    if (!Number.isNaN(utcDate.valueOf())) time.dateTime = utcDate.toISOString();
                    link.append(time);
                }
                row.append(link);
                if (item.source === 'workspace' && number(item.id)) {
                    const read = node('button', 'pbw-notification-read');
                    read.type = 'button'; read.dataset.pbwRead = String(number(item.id));
                    read.title = 'Mark as read'; read.setAttribute('aria-label', 'Mark this notification as read');
                    const icon = node('span', '', '\u2713'); icon.setAttribute('aria-hidden', 'true');
                    read.append(icon); row.append(read);
                }
                contents.push(row);
            });
            if (!items.length) contents.push(node('p', 'pbw-notification-empty', "You're all caught up."));
            wrap.querySelector('.pbw-notification-items')?.replaceChildren(...contents);
            const footer = wrap.querySelector('.pbw-notification-footer');
            const footerChildren = [];
            const historyURL = safeURL(payload.history_url);
            if (historyURL) {
                const history = node('a', '', 'Workspace history'); history.href = historyURL; history.dataset.pbwHistory = '1';
                const all = node('button', 'pbw-notification-mark-all', 'Mark workspace updates read');
                all.type = 'button'; all.dataset.pbwMarkAll = '1'; all.disabled = !number(payload.workspace_unread_count);
                footerChildren.push(history, all);
            }
            footer?.replaceChildren(...footerChildren);
        });
        document.dispatchEvent(new CustomEvent('pbw:bell-updated', {detail: payload}));
        return true;
    }
    async function requestJSON(url, options) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
            const response = await fetch(url, Object.assign({credentials:'same-origin', cache:'no-store', signal:controller.signal}, options));
            if (response.status === 401 || response.status === 403 || response.redirected) {
                const error = new Error('Notification access changed. Reload or sign in again.'); error.denied = true; throw error;
            }
            if (!response.ok) throw new Error('Notifications could not refresh. Try again.');
            return await response.json();
        } finally { clearTimeout(timeout); }
    }
    async function refresh(force) {
        if (inFlight || reading || document.hidden || !wraps().length || (!force && Date.now() - lastRefresh < REFRESH_MS - 1000)) return;
        inFlight = true;
        const ticket = ++sequence;
        try {
            const data = await requestJSON(FEED, {headers:{Accept:'application/json'}});
            if (apply(data, ticket)) { lastRefresh = Date.now(); announce(''); }
        } catch (error) {
            if (error.denied) apply({version:1, items:[], unread_count:0, workspace_unread_count:0, workspace_watermark:0, history_url:false, workspace_summary:{}}, ticket);
            announce(error.denied ? error.message : 'Notifications could not refresh. Your last view is kept; retry by opening the bell.');
        } finally { inFlight = false; }
    }
    function notifyOtherTabs() {
        try { channel?.postMessage({type:'read'}); } catch (_) { /* optional */ }
        try { localStorage.setItem(CHANGE_KEY, String(Date.now())); } catch (_) { /* storage can be disabled */ }
    }
    async function markRead(wrap, params) {
        if (reading) return false;
        const csrf = wrap.dataset.csrf;
        if (!csrf) { announce('Reload this page before marking notifications read.'); return false; }
        reading = true;
        const ticket = ++sequence;
        const form = new URLSearchParams(Object.assign({csrf_token:csrf}, params));
        wraps().forEach(w => w.querySelectorAll('.pbw-notification-read, [data-pbw-mark-all]').forEach(button => { button.disabled = true; }));
        try {
            const data = await requestJSON(READ, {method:'POST', headers:{Accept:'application/json', 'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'}, body:form.toString()});
            if (!apply(data, ticket)) throw new Error('Invalid notification response.');
            lastRefresh = Date.now(); announce(''); notifyOtherTabs(); return true;
        } catch (error) {
            announce(error.denied ? 'This notification is no longer available with your current permissions.' : 'Could not mark notifications read. Please try again.');
            return false;
        } finally {
            reading = false;
            wraps().forEach(w => {
                w.querySelectorAll('.pbw-notification-read').forEach(button => { button.disabled = false; });
                const all = w.querySelector('[data-pbw-mark-all]');
                if (all) all.disabled = !number(w.dataset.workspaceUnread);
            });
        }
    }
    function close(except) {
        wraps().forEach(wrap => {
            if (wrap === except) return;
            const panel = wrap.querySelector('.pbw-notification-panel');
            if (panel) panel.hidden = true;
            wrap.querySelector('.pbw-notification-trigger')?.setAttribute('aria-expanded', 'false');
        });
    }
    function schedule() {
        if (timer === null) timer = setInterval(() => refresh(true), REFRESH_MS);
    }
    function start() {
        if (started || !wraps().length) return;
        started = true;
        wraps().forEach((wrap, index) => {
            const panel = wrap.querySelector('.pbw-notification-panel');
            if (panel) { panel.id = 'pbw-notifications-' + index; wrap.querySelector('.pbw-notification-trigger')?.setAttribute('aria-controls', panel.id); }
        });
        document.addEventListener('click', async event => {
            const wrap = event.target.closest('[data-pbw-bell]');
            if (!wrap) { close(); return; }
            if (event.target.closest('.pbw-notification-trigger')) {
                const panel = wrap.querySelector('.pbw-notification-panel');
                if (!panel) return;
                const open = panel.hidden; close(wrap); panel.hidden = !open;
                wrap.querySelector('.pbw-notification-trigger')?.setAttribute('aria-expanded', String(open));
                if (open) refresh(true);
                return;
            }
            const read = event.target.closest('[data-pbw-read]');
            if (read) { event.preventDefault(); await markRead(wrap, {ident:read.dataset.pbwRead}); return; }
            const all = event.target.closest('[data-pbw-mark-all]');
            if (all) { event.preventDefault(); const upto = number(wrap.dataset.workspaceWatermark); if (upto) await markRead(wrap, {upto_id:String(upto)}); return; }
            const link = event.target.closest('a[data-notice-id]');
            if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && event.button === 0) {
                const target = safeURL(link.getAttribute('href'));
                if (!target) { event.preventDefault(); return; }
                event.preventDefault();
                if (await markRead(wrap, {ident:link.dataset.noticeId})) location.assign(target);
            }
        });
        document.addEventListener('keydown', event => {
            if (event.key !== 'Escape') return;
            const active = wraps().find(wrap => !wrap.querySelector('.pbw-notification-panel')?.hidden);
            close(); active?.querySelector('.pbw-notification-trigger')?.focus();
        });
        document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(true); });
        document.addEventListener('pbw:notifications:refresh', () => refresh(true));
        window.addEventListener('focus', () => refresh(true));
        window.addEventListener('storage', event => { if (event.key === CHANGE_KEY) refresh(true); });
        try { channel = new BroadcastChannel('pbw-notification-read'); channel.onmessage = () => refresh(true); } catch (_) { /* storage event is enough */ }
        window.addEventListener('pagehide', () => { if (timer !== null) clearInterval(timer); timer = null; });
        window.addEventListener('pageshow', () => { schedule(); refresh(true); });
        schedule(); refresh(true);
    }
    window.PbwNotificationBell = {refresh: () => refresh(true)};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
}());
