(function () {
    'use strict';
    function node(tag, cls, text) {
        const el = document.createElement(tag);
        if (cls) el.className = cls;
        if (text !== undefined) el.textContent = String(text);
        return el;
    }
    function refreshSidebar(data) {
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
            if (!e.target.closest('.pbwep-sidebar-profile')) document.getElementById('pbwep-profile-menu')?.classList.remove('show');
        });
        document.addEventListener('pbw:bell-updated', event => {
            refreshSidebar(event.detail?.workspace_summary || {});
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start); else start();
})();
