/** @odoo-module **/

import { Discuss } from "@mail/core/public_web/discuss";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { useState } from "@odoo/owl";

function employeePortalMeta(name) {
    return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") || "";
}

patch(Discuss.prototype, {
    setup() {
        const isEmployeePortalDiscuss = Boolean(employeePortalMeta("employee-portal-discuss"));
        const storeService = this.env.services["mail.store"];
        const originalPublicPage = storeService?.inPublicPage;

        // Odoo's stock public Discuss intentionally opens the selected thread in a
        // ChatWindow on small screens. For employee portal users we want the normal
        // full Discuss thread immediately, like the internal Discuss app. Temporarily
        // disable the public-page flag only while Discuss registers its setup hooks.
        if (isEmployeePortalDiscuss && storeService) {
            storeService.inPublicPage = false;
        }
        super.setup(...arguments);
        if (isEmployeePortalDiscuss && storeService) {
            storeService.inPublicPage = originalPublicPage;
            this.store.discuss.activeTab = "main";
            document.body.classList.add("ep-native-discuss-public");
        }

        this.epDiscuss = useState({
            enabled: isEmployeePortalDiscuss,
            peopleOpen: false,
            peopleLoading: false,
            people: [],
            selected: {},
            error: "",
            saving: false,
        });
    },

    get isEmployeePortalDiscuss() {
        return Boolean(this.epDiscuss?.enabled);
    },

    goEmployeeMessages() {
        window.location.href = employeePortalMeta("employee-portal-back-url") || "/my/employee/discuss";
    },

    goEmployeePortal() {
        window.location.href = employeePortalMeta("employee-portal-home-url") || "/my/employee";
    },

    async openEmployeePeople() {
        if (!this.thread?.id || !this.isEmployeePortalDiscuss) {
            return;
        }
        this.epDiscuss.peopleOpen = true;
        this.epDiscuss.peopleLoading = true;
        this.epDiscuss.error = "";
        this.epDiscuss.selected = {};
        try {
            const result = await rpc("/employee_portal/discuss/available_people", {
                channel_id: this.thread.id,
            });
            this.epDiscuss.people = result?.people || [];
        } catch (error) {
            this.epDiscuss.error = "Unable to load employees.";
        } finally {
            this.epDiscuss.peopleLoading = false;
        }
    },

    closeEmployeePeople() {
        this.epDiscuss.peopleOpen = false;
        this.epDiscuss.error = "";
        this.epDiscuss.selected = {};
    },

    toggleEmployeePerson(userId) {
        this.epDiscuss.selected = {
            ...this.epDiscuss.selected,
            [userId]: !this.epDiscuss.selected[userId],
        };
    },

    async addSelectedEmployees() {
        const userIds = Object.entries(this.epDiscuss.selected)
            .filter(([, selected]) => selected)
            .map(([id]) => Number(id));
        if (!userIds.length || !this.thread?.id) {
            this.epDiscuss.error = "Select at least one employee.";
            return;
        }
        this.epDiscuss.saving = true;
        this.epDiscuss.error = "";
        try {
            const result = await rpc("/employee_portal/discuss/add_people", {
                channel_id: this.thread.id,
                user_ids: userIds,
            });
            if (!result?.ok) {
                this.epDiscuss.error = result?.error || "Unable to add employees.";
                return;
            }
            if (result.redirect) {
                window.location.href = result.redirect;
                return;
            }
            // Reload the native Discuss Store so Odoo's own member panel / RTC state
            // immediately reflects the newly-added employee.
            window.location.reload();
        } catch (error) {
            this.epDiscuss.error = "Unable to add employees.";
        } finally {
            this.epDiscuss.saving = false;
        }
    },

    async toggleEmployeeFullscreen() {
        try {
            if (!document.fullscreenElement) {
                await document.documentElement.requestFullscreen?.();
            } else {
                await document.exitFullscreen?.();
            }
        } catch (_) {
            // Fullscreen is optional (not supported by every mobile browser).
        }
    },
});
