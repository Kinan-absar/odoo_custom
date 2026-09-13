/** @odoo-module **/

// PWA shell for the existing native Odoo Discuss experience.
// No chat, attachment, voice-note, presence or RTC logic is duplicated here.
// Those remain entirely owned by Odoo Discuss.

(() => {
    const isDiscussSurface = () => window.location.pathname.startsWith('/my/employee/discuss');
    if (!isDiscussSurface()) return;

    let deferredInstallPrompt = null;

    function addHeadMetadata() {
        if (!document.querySelector('link[rel="manifest"][data-employee-discuss-pwa]')) {
            const link = document.createElement('link');
            link.rel = 'manifest';
            link.href = '/my/employee/discuss/manifest.webmanifest';
            link.dataset.employeeDiscussPwa = '1';
            document.head.appendChild(link);
        }
        let theme = document.querySelector('meta[name="theme-color"][data-employee-discuss-pwa]');
        if (!theme) {
            theme = document.createElement('meta');
            theme.name = 'theme-color';
            theme.content = '#ffffff';
            theme.dataset.employeeDiscussPwa = '1';
            document.head.appendChild(theme);
        }
        if (!document.querySelector('meta[name="apple-mobile-web-app-capable"]')) {
            const capable = document.createElement('meta');
            capable.name = 'apple-mobile-web-app-capable';
            capable.content = 'yes';
            document.head.appendChild(capable);
        }
        if (!document.querySelector('meta[name="apple-mobile-web-app-title"]')) {
            const title = document.createElement('meta');
            title.name = 'apple-mobile-web-app-title';
            title.content = 'Chats';
            document.head.appendChild(title);
        }
    }

    function applyAppMode() {
        const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
        document.documentElement.classList.toggle('ep-discuss-pwa-standalone', standalone);
        document.body?.classList.toggle('ep-discuss-pwa-standalone', standalone);
    }

    function refreshInstallButtons() {
        const installed = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
        document.querySelectorAll('[data-ep-discuss-install]').forEach((button) => {
            button.classList.toggle('d-none', installed);
            button.disabled = false;
            button.title = installed ? 'Chats is installed' : 'Install Chats';
        });
    }

    async function installChats() {
        if (deferredInstallPrompt) {
            deferredInstallPrompt.prompt();
            try {
                await deferredInstallPrompt.userChoice;
            } finally {
                deferredInstallPrompt = null;
                refreshInstallButtons();
            }
            return;
        }
        const isiOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
        if (isiOS) {
            window.alert('On iPhone/iPad: open this page in Safari, tap Share, then choose “Add to Home Screen”.');
        } else {
            window.alert('Use your browser menu and choose “Install Chats” or “Install app”.');
        }
    }


    function bindHomePage() {
        const newChat = document.getElementById('ep-native-new-chat');
        document.querySelectorAll('[data-ep-new-chat-toggle]').forEach((button) => {
            if (button.dataset.epBound === '1') return;
            button.dataset.epBound = '1';
            button.addEventListener('click', () => newChat?.classList.toggle('show'));
        });
        document.querySelectorAll('[data-ep-new-chat-close]').forEach((button) => {
            if (button.dataset.epBound === '1') return;
            button.dataset.epBound = '1';
            button.addEventListener('click', () => newChat?.classList.remove('show'));
        });
        document.querySelectorAll('[data-ep-chat-search]').forEach((input) => {
            if (input.dataset.epBound === '1') return;
            input.dataset.epBound = '1';
            input.addEventListener('input', () => {
                const query = (input.value || '').trim().toLowerCase();
                let visible = 0;
                document.querySelectorAll('[data-ep-thread]').forEach((thread) => {
                    const show = !query || (thread.dataset.search || '').includes(query);
                    thread.classList.toggle('d-none', !show);
                    if (show) visible += 1;
                });
                document.querySelector('[data-ep-search-empty]')?.classList.toggle('d-none', visible !== 0 || !query);
            });
        });
    }

    function bindInstallButtons() {
        document.querySelectorAll('[data-ep-discuss-install]').forEach((button) => {
            if (button.dataset.epInstallBound === '1') return;
            button.dataset.epInstallBound = '1';
            button.addEventListener('click', (event) => {
                event.preventDefault();
                installChats();
            });
        });
        refreshInstallButtons();
    }

    addHeadMetadata();
    applyAppMode();

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/my/employee/discuss/sw.js', { scope: '/my/employee/discuss' }).catch((error) => {
                console.warn('Chats PWA service worker registration failed', error);
            });
        }, { once: true });
    }

    window.addEventListener('beforeinstallprompt', (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;
        refreshInstallButtons();
    });
    window.addEventListener('appinstalled', () => {
        deferredInstallPrompt = null;
        refreshInstallButtons();
    });

    document.addEventListener('DOMContentLoaded', () => { bindInstallButtons(); bindHomePage(); });
    window.addEventListener('pageshow', () => {
        applyAppMode();
        bindInstallButtons();
        bindHomePage();
    });

    // Expose only the install action to the native Owl toolbar patch.
    window.EmployeeDiscussPWA = { install: installChats };
})();
