/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { user } from "@web/core/user";

function connectTelegramItem(env) {
    return {
        type: "item",
        id: "employee_portal_connect_telegram",
        description: _t("Connect Telegram"),
        show: () => Boolean(
            session.employee_portal_telegram_connect_available &&
            !session.employee_portal_telegram_connected
        ),
        callback: async () => {
            const action = await env.services.orm.call(
                "res.users",
                "action_connect_telegram",
                [[user.userId]]
            );
            if (action) {
                await env.services.action.doAction(action);
            }
        },
        sequence: 55,
    };
}

registry.category("user_menuitems").add(
    "employee_portal_connect_telegram",
    connectTelegramItem
);
