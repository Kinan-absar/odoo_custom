/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { HomeMenu } from "@web_enterprise/webclient/home_menu/home_menu";
import { markup, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

patch(HomeMenu.prototype, {
    setup() {
        super.setup(...arguments);

        this.orm = useService("orm");
        this.annState = useState({
            announcements: [],
            activeIndex: 0,
        });

        onWillStart(async () => {
            try {
                const result = await this.orm.call(
                    "portal.announcement",
                    "get_backend_announcements",
                    []
                );
                this.annState.announcements = result.map((ann) => ({
                    ...ann,
                    message: markup(ann.message || ""),
                }));
            } catch {
                this.annState.announcements = [];
            }
        });
    },

    annSetActive(index) {
        this.annState.activeIndex = index;
    },

    annPrev() {
        const len = this.annState.announcements.length;
        this.annState.activeIndex = (this.annState.activeIndex - 1 + len) % len;
    },

    annNext() {
        const len = this.annState.announcements.length;
        this.annState.activeIndex = (this.annState.activeIndex + 1) % len;
    },
});
