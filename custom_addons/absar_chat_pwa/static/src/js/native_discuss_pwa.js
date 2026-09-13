/** @odoo-module **/

function isAbsarChatDiscuss() {
    return Boolean(document.querySelector('meta[name="absar-chat-pwa"]'));
}

function applyAbsarChatShell() {
    if (!isAbsarChatDiscuss()) return;

    // Keep the native Discuss page in a light theme without changing the user's
    // global Odoo appearance preference.
    document.documentElement.classList.add('absar-chat-pwa-native');
    document.documentElement.setAttribute('data-bs-theme', 'light');
    document.documentElement.classList.remove('o_dark');
    if (document.body) {
        document.body.classList.add('absar-chat-pwa-native');
        document.body.classList.remove('o_dark');
        document.body.setAttribute('data-bs-theme', 'light');
    }

    // The existing Employee Portal Discuss patch reads these meta tags when the
    // toolbar buttons are clicked. Repoint only the PWA conversation's Back action.
    const back = document.querySelector('meta[name="employee-portal-back-url"]');
    if (back) back.setAttribute('content', '/chat/');

    // Keep an Absar Chat title in the installed app window.
    document.title = 'Absar Chat';
}

applyAbsarChatShell();
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyAbsarChatShell, { once: true });
}
