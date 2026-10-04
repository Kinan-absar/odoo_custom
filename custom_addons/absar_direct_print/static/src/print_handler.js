/** @odoo-module **/
import { registry } from "@web/core/registry";
registry.category("ir.actions.report handlers").add("absar_direct_print", async (action, options, env) => {
    if (action.report_type !== "qweb-pdf" || action.context?.absar_skip_print) return false;
    const prefs = await env.services.orm.call("res.users", "absar_print_preferences", []);
    if (!prefs.enabled) return false;
    const wizard = await env.services.orm.call("absar.print.wizard", "open_report", [action]);
    await env.services.action.doAction(wizard);
    return true;
}, { sequence: 5 });
