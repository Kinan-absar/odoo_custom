/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

function chatsMenuItem() {
    return {
        type: "item",
        id: "absar_chats_pwa",
        description: _t("Chats"),
        callback: () => {
            window.open("/chat/", "_blank", "noopener");
        },
        sequence: 48,
    };
}

registry.category("user_menuitems").add("absar_chats_pwa", chatsMenuItem);
