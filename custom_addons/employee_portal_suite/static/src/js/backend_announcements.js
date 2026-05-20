/** @odoo-module **/

import { registry } from "@web/core/registry";

const backendAnnouncementService = {
    dependencies: ["orm", "notification"],

    async start(env, { orm, notification }) {
        let announcements = [];
        try {
            announcements = await orm.call(
                "portal.announcement",
                "get_backend_announcements",
                []
            );
        } catch (error) {
            return;
        }

        for (const ann of announcements) {
            notification.add(ann.message || "", {
                title: ann.title || "Announcement",
                type: ann.type || "info",
                sticky: true,
            });
        }
    },
};

registry.category("services").add("employee_portal_backend_announcements", backendAnnouncementService);
