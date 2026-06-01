/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, markup, onWillStart, useState, useRef, useEffect } from "@odoo/owl";

class AnnouncementSystray extends Component {
    static template = "employee_portal_suite.AnnouncementSystray";
    static props = [];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            announcements: [],
            open: false,
        });
        this.dropdownRef = useRef("dropdown");

        onWillStart(async () => {
            await this._loadAnnouncements();
        });

        // Close dropdown when clicking outside
        useEffect(() => {
            const handler = (e) => {
                const el = this.dropdownRef.el;
                if (el && !el.contains(e.target)) {
                    this.state.open = false;
                }
            };
            document.addEventListener("mousedown", handler);
            return () => document.removeEventListener("mousedown", handler);
        });
    }

    async _loadAnnouncements() {
        try {
            const result = await this.orm.call(
                "portal.announcement",
                "get_backend_announcements",
                []
            );
            this.state.announcements = result.map((ann) => ({
                ...ann,
                message: markup(ann.message || ""),
            }));
        } catch {
            this.state.announcements = [];
        }
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    get count() {
        return this.state.announcements.length;
    }
}

registry.category("systray").add("announcement_systray", {
    Component: AnnouncementSystray,
}, { sequence: 99 }); // 99 = just before messages (100) so it sits right next to it

export default AnnouncementSystray;
