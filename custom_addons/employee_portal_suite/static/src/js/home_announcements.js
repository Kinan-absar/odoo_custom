/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";
import { markup, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(HomeMenu.prototype, {
    setup() {
        super.setup(...arguments);

        this.orm = useService("orm");
        this.backendAnnouncementState = useState({
            announcements: [],
            collapsed: true,   // panel starts open
        });

        onWillStart(async () => {
            try {
                const announcements = await this.orm.call(
                    "portal.announcement",
                    "get_backend_announcements",
                    []
                );
                this.backendAnnouncementState.announcements = announcements.map((ann) => ({
                    ...ann,
                    message: markup(ann.message || ""),
                }));
            } catch (error) {
                this.backendAnnouncementState.announcements = [];
            }
        });
    },

    toggleAnnouncements() {
        this.backendAnnouncementState.collapsed = !this.backendAnnouncementState.collapsed;
    },
});
