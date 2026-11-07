/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

const menuRegistry = registry.category("user_menuitems");

function removeRetiredAbsarChatShortcut() {
    // absar_chat_pwa used this key for the retired /chat/ application.
    // Keep only the native Discuss/PWA shortcut below.
    try {
        if (menuRegistry.contains("absar_chats_pwa")) {
            menuRegistry.remove("absar_chats_pwa");
        }
    } catch (_) {
        // The retired module may already be uninstalled.
    }
}

// Remove it now and again after all backend bundles have had a chance to register
// their user-menu entries. This handles the migration period while the old addon
// is still installed without touching any Odoo core menu.
removeRetiredAbsarChatShortcut();
for (const delay of [0, 250, 1000, 2500]) {
    window.setTimeout(removeRetiredAbsarChatShortcut, delay);
}

function nativeChatsMenuItem() {
    return {
        type: "item",
        id: "employee_native_discuss_chats",
        description: _t("Chats"),
        callback: () => {
            window.location.href = "/odoo/discuss";
        },
        sequence: 48,
    };
}

menuRegistry.add("employee_native_discuss_chats", nativeChatsMenuItem, { force: true });
