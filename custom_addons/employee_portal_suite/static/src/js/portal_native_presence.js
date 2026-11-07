/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Keep Employee Portal users on Odoo's native bus.presence while they are
 * anywhere in /my/employee.  This is deliberately not a second presence
 * system: it sends the same websocket `update_presence` event used by Odoo.
 */
const employeePortalNativePresence = {
    dependencies: ["bus_service", "presence"],
    async start(env, { bus_service, presence }) {
        if (!window.location.pathname.startsWith("/my/employee")) {
            return;
        }

        let stopped = false;
        const sendPresence = () => {
            if (stopped) return;
            bus_service.send("update_presence", {
                inactivity_period: presence.getInactivityPeriod(),
                im_status_ids_by_model: {},
            });
        };

        // Native presence updates travel through the websocket, so make sure
        // the frontend bus is active even when the employee never opens Discuss.
        await bus_service.start();
        sendPresence();

        // Odoo's bus.presence expects a refresh at least every 60 seconds.
        const timer = window.setInterval(sendPresence, 50000);
        presence.bus.addEventListener("presence", sendPresence);
        env.bus.addEventListener("window_focus", sendPresence);

        return () => {
            stopped = true;
            window.clearInterval(timer);
            presence.bus.removeEventListener("presence", sendPresence);
            env.bus.removeEventListener("window_focus", sendPresence);
        };
    },
};

registry.category("services").add("employee_portal.native_presence", employeePortalNativePresence);
