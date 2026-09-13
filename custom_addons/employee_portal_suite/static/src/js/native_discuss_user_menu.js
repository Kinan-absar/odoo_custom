/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

const menuRegistry = registry.category("user_menuitems");

// If the retired absar_chat_pwa module is still installed during migration,
// hide its old /chat/ shortcut so internal users do not get sent to the obsolete UI.
try {
    if (menuRegistry.contains("absar_chats_pwa")) {
        menuRegistry.remove("absar_chats_pwa");
    }
} catch (_) {
    // Safe on databases where that registry item never existed.
}

function nativeChatsMenuItem() {
    return {
        type: "item",
        id: "employee_native_discuss_chats",
        description: _t("Chats"),
        callback: () => {
            window.open("/my/employee/discuss", "_blank", "noopener");
        },
        sequence: 48,
    };
}

menuRegistry.add("employee_native_discuss_chats", nativeChatsMenuItem, { force: true });
