/** @odoo-module **/

import { registry } from "@web/core/registry";

registry.category("services").add("employee_portal_discuss_bridge", {
    dependencies: ["bus_service", "notification"],
    start(env, { bus_service, notification }) {
        let reloadTimer = null;
        try {
            bus_service.subscribe("employee_portal_discuss_bridge", (payload) => {
                const author = payload && payload.author ? payload.author : "Employee";
                const preview = payload && payload.preview ? payload.preview : "New message";
                notification.add(`${author}: ${preview}`, {
                    title: "New message",
                    type: "info",
                });

                // Native Discuss normally updates through its own Store bus events.
                // If a portal-created channel was not known to the already-open Store,
                // refresh only an actively-open Discuss screen as a safe fallback.
                const discussOpen = Boolean(
                    document.querySelector(".o-mail-Discuss, .o-mail-Discuss-content") ||
                    String(window.location.hash || "").toLowerCase().includes("discuss")
                );
                const active = document.activeElement;
                const composing = Boolean(active && (
                    active.tagName === "INPUT" || active.tagName === "TEXTAREA" ||
                    active.isContentEditable
                ));
                if (discussOpen && !composing) {
                    window.clearTimeout(reloadTimer);
                    reloadTimer = window.setTimeout(() => window.location.reload(), 500);
                }
            });
        } catch (error) {
            console.warn("[Employee Portal] Discuss bridge unavailable", error);
        }
        return {};
    },
});
