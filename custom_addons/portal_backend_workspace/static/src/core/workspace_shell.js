(function () {
    'use strict';
    let activeRequest = false, lastRefresh = 0;
    window.togglePbwBell = function (event) {
        event.stopPropagation();
        const panel = event.currentTarget.closest('.pbwep-bell-wrap')?.querySelector('.pbwep-bell-panel');
        if (!panel) return;
        document.querySelectorAll('.pbwep-bell-panel.show').forEach(p => { if (p !== panel) p.classList.remove('show'); });
        panel.classList.toggle('show');
        refresh();
    };
    function node(tag, cls, text) {
        const el = document.createElement(tag);
        if (cls) el.className = cls;
        if (text !== undefined) el.textContent = String(text);
        return el;
    }
    async function refresh() {
        if (activeRequest || document.hidden || Date.now() - lastRefresh < 10000) return;
        activeRequest = true;
        try {
            const response = await fetch('/my/workspace/notifications/summary', {credentials: 'same-origin', headers: {'Accept':'application/json'}, cache:'no-store'});
            if (!response.ok) return;
            const data = await response.json();
            if (!data || typeof data !== 'object' || Array.isArray(data)) return;
            lastRefresh = Date.now();
            const badgeTypes = {
                '/my/workspace/sales/approvals':['sales_approval','count'],
                '/my/workspace/sales/updates':['sales_review_update','new'],
                '/my/workspace/purchase/approvals':['purchase_approval','count'],
                '/my/workspace/accounting':['accounting_approval','count'],
            };
            document.querySelectorAll('#pbwep-desktop-sidebar-nav a.pbwep-sidebar-link').forEach(link => {
                const spec = badgeTypes[new URL(link.href,location.origin).pathname];
                if (!spec) return;
                const count = Math.max(0, Number(data[spec[0]]?.[spec[1]]) || 0);
                let badge = link.querySelector('.pbw-navigation-count');
                if (count && !badge) { badge = node('span','pbw-navigation-count'); link.append(badge); }
                if (badge) { badge.textContent = String(count); badge.hidden = !count; }
            });
            const items = Object.entries(data).filter(([,v]) => v && Number(v.new) > 0 && typeof v.url === 'string' && v.url.startsWith('/my/workspace'));
            document.querySelectorAll('.pbwep-bell-wrap').forEach(wrap => {
                const btn = wrap.querySelector('.pbwep-bell-btn'), panel = wrap.querySelector('.pbwep-bell-panel');
                if (!btn || !panel) return;
                btn.classList.toggle('has-unread', !!items.length);
                btn.querySelectorAll('.pbwep-bell-dot').forEach(el => el.remove());
                if (items.length) btn.append(node('span','pbwep-bell-dot'));
                const contents = [node('div','pbwep-bell-panel-header','Notifications')];
                for (const [kind,value] of items) {
                    const a = node('a','pbwep-bell-item'); a.href = value.url; a.dataset.pbwNotificationKind = kind;
                    const icon = node('div','pbwep-bell-item-icon'); icon.append(node('i','fa fa-bell'));
                    a.append(icon,node('span','pbwep-bell-item-label',value.label || kind),node('span','pbwep-bell-item-count',Number(value.new)+' new'));
                    contents.push(a);
                }
                if (!items.length) contents.push(node('div','pbwep-bell-empty',"You're all caught up."));
                panel.replaceChildren(...contents);
            });
        } catch (_) {
            // Keep server-rendered notifications on temporary network/session failure.
        } finally { activeRequest = false; }
    }
    function start() {
        if (!document.getElementById('pbwep-shared-sidebar')) return;
        document.body.classList.add('pbw-workspace-page');
        const fabMenu = document.getElementById('pbwFabMenu');
        const fabButton = document.getElementById('pbwFabCenterBtn');
        function closeFab() {
            fabMenu?.classList.remove('show');
            fabButton?.classList.remove('fab-open');
            fabButton?.setAttribute('aria-expanded', 'false');
        }
        if (fabButton && fabMenu) {
            if (!fabMenu.querySelector('a[href]')) fabButton.hidden = true;
            fabButton.addEventListener('click', () => {
                const open = fabMenu.classList.toggle('show');
                fabButton.classList.toggle('fab-open', open);
                fabButton.setAttribute('aria-expanded', String(open));
            });
            document.addEventListener('click', e => {
                if (!e.target.closest('#pbwFabMenu, #pbwFabCenterBtn')) closeFab();
            });
            document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFab(); });
        }
        const path = location.pathname.replace(/\/$/, '');
        let selected = null;
        document.querySelectorAll('#pbwep-desktop-sidebar-nav a.pbwep-sidebar-link').forEach(a => {
            const p = new URL(a.href,location.origin).pathname.replace(/\/$/, '');
            if (path === p || (p !== '/my/workspace' && path.startsWith(p+'/'))) {
                if (!selected || p.length > new URL(selected.href).pathname.length) selected = a;
            }
        });
        if (selected) selected.classList.add('active');
        document.addEventListener('click', e => {
            if (!e.target.closest('.pbwep-bell-wrap')) document.querySelectorAll('.pbwep-bell-panel.show').forEach(p => p.classList.remove('show'));
            if (!e.target.closest('.pbwep-sidebar-profile')) document.getElementById('pbwep-profile-menu')?.classList.remove('show');
        });
        document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.pbwep-bell-panel.show').forEach(p => p.classList.remove('show')); });
        document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
        window.addEventListener('focus', refresh);
        const timer = window.setInterval(refresh, 60000);
        window.addEventListener('pagehide', () => window.clearInterval(timer), {once:true});
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start); else start();
})();
