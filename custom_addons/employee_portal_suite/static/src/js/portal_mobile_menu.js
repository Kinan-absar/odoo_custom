/** Mobile navigation uses the actual desktop sidebar, including installed bridge links. */
(function () {
    function start() {
        const sidebar = document.getElementById('ep-shared-sidebar');
        const backdrop = document.querySelector('.ep-mobile-menu-backdrop');
        const toggles = Array.from(document.querySelectorAll('.ep-mobile-menu-toggle'));
        if (!sidebar || !backdrop || !toggles.length || sidebar.dataset.mobileMenuReady) return;
        sidebar.dataset.mobileMenuReady = '1';
        const mobile = window.matchMedia('(max-width: 768px)');
        let opener = null, previousOverflow = '', open = false;
        // Enhance only the existing, permission-filtered section headings.
        function configureSections() {
            sidebar.querySelectorAll('.ep-sidebar-section').forEach(section => {
                const title = section.querySelector('.ep-sidebar-section-title');
                if (!title) return;
                if (!section.dataset.epMenuSectionReady) {
                    section.dataset.epMenuSectionReady = '1';
                    const current = section.querySelector('a.active') ||
                        Array.from(section.querySelectorAll('a[href]')).find(link =>
                            link.getAttribute('href')?.split('?')[0] === window.location.pathname);
                    section.dataset.epCollapsed = current || section.id === 'ep-section-my-work' ? 'false' : 'true';
                    const toggleSection = () => {
                        if (!mobile.matches) return;
                        section.dataset.epCollapsed = section.dataset.epCollapsed === 'true' ? 'false' : 'true';
                        title.setAttribute('aria-expanded', String(section.dataset.epCollapsed !== 'true'));
                    };
                    title.addEventListener('click', toggleSection);
                    title.addEventListener('keydown', event => {
                        if (mobile.matches && (event.key === 'Enter' || event.key === ' ')) {
                            event.preventDefault(); toggleSection();
                        }
                    });
                }
                if (mobile.matches) {
                    title.setAttribute('role', 'button');
                    title.setAttribute('tabindex', '0');
                    title.setAttribute('aria-expanded', String(section.dataset.epCollapsed !== 'true'));
                } else {
                    ['role', 'tabindex', 'aria-expanded'].forEach(key => title.removeAttribute(key));
                }
            });
        }
        configureSections();
        const navigation = document.getElementById('ep-desktop-sidebar-nav');
        if (navigation) new MutationObserver(configureSections).observe(navigation, {childList:true, subtree:true});
        const focusable = () => Array.from(sidebar.querySelectorAll('a[href],button:not([disabled]),[tabindex="0"]'))
            .filter(node => node.getClientRects().length);
        function close(restoreFocus = true) {
            if (!open) return;
            open = false;
            sidebar.classList.remove('ep-mobile-menu-open');
            sidebar.removeAttribute('role');
            sidebar.removeAttribute('aria-modal');
            backdrop.hidden = true;
            toggles.forEach(button => button.setAttribute('aria-expanded', 'false'));
            document.body.style.overflow = previousOverflow;
            if (restoreFocus && mobile.matches && opener) opener.focus();
        }
        function show(button) {
            if (!mobile.matches) return;
            if (open) { close(); return; }
            opener = button;
            previousOverflow = document.body.style.overflow;
            open = true;
            sidebar.classList.add('ep-mobile-menu-open');
            sidebar.setAttribute('role', 'dialog');
            sidebar.setAttribute('aria-modal', 'true');
            backdrop.hidden = false;
            toggles.forEach(node => node.setAttribute('aria-expanded', 'true'));
            document.body.style.overflow = 'hidden';
            // Keep the Create popup separate from navigation.
            document.getElementById('fabMenu')?.classList.remove('show');
            document.getElementById('fabCenterBtn')?.classList.remove('fab-open');
            focusable()[0]?.focus();
        }
        toggles.forEach(button => button.addEventListener('click', () => show(button)));
        document.querySelectorAll('[data-ep-menu-close]').forEach(button =>
            button.addEventListener('click', () => close()));
        sidebar.addEventListener('click', event => {
            if (event.target.closest('a[href]')) close(false);
        });
        document.addEventListener('keydown', event => {
            if (!open) return;
            if (event.key === 'Escape') { event.preventDefault(); close(); }
            if (event.key === 'Tab') {
                const nodes = focusable(), first = nodes[0], last = nodes[nodes.length - 1];
                if (!first) { event.preventDefault(); return; }
                if (event.shiftKey && (document.activeElement === first || !sidebar.contains(document.activeElement))) {
                    event.preventDefault(); last.focus();
                } else if (!event.shiftKey && (document.activeElement === last || !sidebar.contains(document.activeElement))) {
                    event.preventDefault(); first.focus();
                }
            }
        });
        mobile.addEventListener('change', () => { configureSections(); if (!mobile.matches) close(false); });
        window.addEventListener('pagehide', () => close(false));
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
