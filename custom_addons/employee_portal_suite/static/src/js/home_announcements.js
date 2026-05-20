/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";
import { onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(HomeMenu.prototype, {
    setup() {
        super.setup(...arguments);

        this.orm = useService("orm");
        this.backendAnnouncementState = useState({
            announcements: [],
        });

        onWillStart(async () => {
            try {
                const announcements = await this.orm.call(
                    "portal.announcement",
                    "get_backend_announcements",
                    []
                );
                this.backendAnnouncementState.announcements = announcements || [];
            } catch (error) {
                this.backendAnnouncementState.announcements = [];
            }
        });
    },
});
