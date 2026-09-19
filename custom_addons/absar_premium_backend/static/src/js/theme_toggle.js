/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const BODY_CLASS = "absar-premium-theme";

function applyTheme(enabled) {
    document.body.classList.toggle(BODY_CLASS, Boolean(enabled));
    document.documentElement.classList.toggle(BODY_CLASS, Boolean(enabled));
    window.__absarPremiumThemeEnabled = Boolean(enabled);
}

const absarThemeService = {
    dependencies: ["orm"],
    async start(env, { orm }) {
        try {
            const enabled = await orm.call("res.users", "absar_get_theme_enabled", []);
            applyTheme(enabled);
        } catch (error) {
            // Fail safe: keep Odoo usable even if the preference cannot be read.
            applyTheme(false);
        }
        return { applyTheme };
    },
};

registry.category("services").add("absar_premium_theme", absarThemeService);

registry.category("user_menuitems").add("absar_premium_theme_toggle", (env) => {
    const enabled = document.body.classList.contains(BODY_CLASS);
    return {
        description: enabled ? _t("Premium Theme: On") : _t("Premium Theme: Off"),
        sequence: 65,
        callback: async () => {
            const next = !document.body.classList.contains(BODY_CLASS);
            await env.services.orm.call("res.users", "absar_set_theme_enabled", [next]);
            applyTheme(next);
            env.services.notification.add(
                next ? _t("Premium theme enabled") : _t("Premium theme disabled"),
                { type: "success" }
            );
        },
    };
});
