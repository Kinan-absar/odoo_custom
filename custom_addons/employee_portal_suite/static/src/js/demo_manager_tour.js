/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY = "eps_demo_manager_tour";
const HIGHLIGHT_CLASS = "eps_demo_tour_highlight";

const STEPS = [
    {
        title: "Welcome to Employee Portal Suite",
        text: "This tour follows the current setup model: create/link the portal employee, assign the employee's manager and work location, connect the location to a project, then configure built-in permissions, reusable Approval Roles, project-specific role assignments, and separate ER/MR approval workflows before testing the employee portal.",
    },
    {
        title: "1. Start from the Employee Contact",
        text: "Every portal employee starts from a Contact. We will use Demo Employee One. Open the contact first, then grant portal access from the Action menu.",
        target: "demo_contact",
    },
    {
        title: "2. Grant Portal Access",
        text: "On the Contact, open the Action menu and choose Grant Portal Access. This creates the external portal login. Portal users do not consume an internal Odoo user seat.",
        target: "demo_contact",
        focus: "grant_portal",
    },
    {
        title: "3. Open the Matching Employee",
        text: "Now open the matching Employee record. The Employee record connects the portal login to HR information, the direct manager, department and assigned work locations/projects.",
        target: "demo_employee",
    },
    {
        title: "4. Link the Related User",
        text: "On the Employee, open Settings and set Related User to the portal user created from the Contact. This link tells Employee Portal Suite which employee belongs to the logged-in portal account.",
        target: "demo_employee",
        focus: "related_user",
    },
    {
        title: "5. Department, Direct Manager & Work Locations",
        text: "Open Work Information. Set the Department and Direct Manager, then assign the employee's Work Location(s). The direct manager can be used as a dynamic ER workflow step, while work locations determine which projects the employee can select in ER/MR requests.",
        target: "demo_employee",
        focus: "work_information",
    },
    {
        title: "6. Open the Employee Work Location",
        text: "Demo Project Site is assigned to this employee. Open the Work Location to see how locations are connected to projects and optional attendance geofencing.",
        target: "demo_work_location",
        focus: "work_location_header",
    },
    {
        title: "7. Link Project & Geofence",
        text: "Under Projects and Geolocation, link the project(s) that belong to this Work Location. Employees can select only projects reached through their assigned work locations. Geofencing can optionally enforce attendance latitude, longitude and radius.",
        target: "demo_work_location",
        focus: "project_geofence",
    },
    {
        title: "8. Built-in Roles & Permissions",
        text: "Open Configuration → Roles & Permissions. These are the built-in access roles such as Manager, HR, Finance, CEO, Attendance Manager and Material Request roles. They control what a user is allowed to see or administer; roles are additive.",
        target: "roles_permissions",
    },
    {
        title: "9. Create Your Own Approval Roles",
        text: "Open Configuration → Approval Roles. This is where a company can create its own business approval positions—Commercial Manager, Cost Control, Site Engineer, Operations Director, or any other role—without adding new hard-coded groups.",
        target: "approval_roles",
    },
    {
        title: "10. Assign Approval Roles per Project",
        text: "Open Project Role Assignments. Assign the actual users who perform each Approval Role on each project. The same role can resolve to different people on different projects.",
        target: "project_role_assignments",
    },
    {
        title: "11. Design ER & MR Workflows",
        text: "Open Workflows. Create a separate workflow for Employee Requests or Material Requests, optionally per project and ER request type. Add as many ordered steps as needed. A step can use the employee's Direct Manager, a custom Approval Role, a specific user, Project Manager, Store Manager, or other supported resolver. If no matching custom workflow exists, the existing default/legacy flow remains the fallback.",
        target: "workflows",
    },
    {
        title: "12. Employee Request Approval Flow",
        text: "Open Employee Requests and review the demo records. In a custom ER workflow, the first step can always resolve to the employee's Direct Manager, followed by HR, Finance, CEO, custom Approval Roles, or any other sequence you configure.",
        target: "employee_requests",
    },
    {
        title: "13. Material Request Approval Flow",
        text: "Open Material Requests and review the demo records. MR workflows are project-aware: the request project determines which project workflow and project-role assignments are used. Custom workflows can replace the old fixed Purchase/Store/Project Manager/Director/CEO chain.",
        target: "material_requests",
    },
    {
        title: "14. Experience the Employee Portal",
        text: "The setup is complete. Open the Employee Portal in a new tab and log in as employee1@eps-demo.local. Test ER/MR submission, assigned projects, attendance, reports, announcements, messaging and approvals, then return as Demo Manager to configure or approve records.",
        portal: true,
    },
];

class EPSDemoManagerTourOverlay extends Component {
    static template = "employee_portal_suite.EPSDemoManagerTourOverlay";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ visible: false, active: false, step: 0 });

        onMounted(async () => {
            this._installHighlightStyle();
            await this._computeVisibility();
            if (!this.state.visible) return;
            const saved = window.localStorage.getItem(STORAGE_KEY);
            if (saved) {
                try {
                    const data = JSON.parse(saved);
                    this.state.active = Boolean(data.active);
                    const step = Number(data.step);
                    this.state.step = Number.isFinite(step) ? Math.max(0, Math.min(step, STEPS.length - 1)) : 0;
                } catch (_) {
                    window.localStorage.removeItem(STORAGE_KEY);
                }
            }
            if (this.state.active) {
                setTimeout(() => this._applyFocus(), 450);
            }
        });
    }

    _installHighlightStyle() {
        if (document.getElementById("eps_demo_tour_style")) return;
        const style = document.createElement("style");
        style.id = "eps_demo_tour_style";
        style.textContent = `
            .${HIGHLIGHT_CLASS} {
                position: relative !important;
                z-index: 10040 !important;
                outline: 3px solid #875a7b !important;
                outline-offset: 4px !important;
                border-radius: 6px !important;
                box-shadow: 0 0 0 8px rgba(135,90,123,.14), 0 0 24px rgba(135,90,123,.38) !important;
                animation: epsTourPulse 1.5s ease-in-out infinite;
            }
            @keyframes epsTourPulse {
                0%, 100% { box-shadow: 0 0 0 7px rgba(135,90,123,.12), 0 0 18px rgba(135,90,123,.28); }
                50% { box-shadow: 0 0 0 11px rgba(135,90,123,.20), 0 0 30px rgba(135,90,123,.45); }
            }
        `;
        document.head.appendChild(style);
    }

    async _computeVisibility() {
        try {
            const demoUsers = await this.orm.searchRead("res.users", [["login", "=", "manager@eps-demo.local"]], ["id"], { limit: 1 });
            this.state.visible = Boolean(demoUsers.length);
        } catch (_) {
            this.state.visible = false;
        }
    }

    get current() { return STEPS[this.state.step]; }
    get total() { return STEPS.length; }

    _save() {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ active: this.state.active, step: this.state.step }));
    }

    start() {
        this.state.active = true;
        if (!Number.isFinite(this.state.step)) this.state.step = 0;
        this._save();
        setTimeout(() => this._applyFocus(), 200);
    }

    collapse() {
        this._clearHighlight();
        this.state.active = false;
        this._save();
    }

    restart() {
        this._clearHighlight();
        this.state.step = 0;
        this.state.active = true;
        this._save();
    }

    async _findOne(model, domain) {
        const records = await this.orm.searchRead(model, domain, ["id"], { limit: 1 });
        return records.length ? records[0].id : false;
    }

    async _openForm(model, resId, name) {
        if (!resId) {
            this.notification.add(`${name} was not found. Run Prepare / Reset Demo first.`, { type: "warning" });
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    _clearHighlight() {
        document.querySelectorAll(`.${HIGHLIGHT_CLASS}`).forEach((el) => el.classList.remove(HIGHLIGHT_CLASS));
    }

    async _waitFor(selector, timeout = 4500) {
        const started = Date.now();
        while (Date.now() - started < timeout) {
            const el = document.querySelector(selector);
            if (el) return el;
            await new Promise((resolve) => setTimeout(resolve, 120));
        }
        return null;
    }

    async _clickTab(text) {
        const deadline = Date.now() + 3500;
        while (Date.now() < deadline) {
            const candidates = [...document.querySelectorAll(".nav-link, .o_notebook_headers a, .o_notebook_headers button")];
            const tab = candidates.find((el) => (el.textContent || "").trim().toLowerCase() === text.toLowerCase());
            if (tab) {
                tab.click();
                await new Promise((resolve) => setTimeout(resolve, 300));
                return tab;
            }
            await new Promise((resolve) => setTimeout(resolve, 120));
        }
        return null;
    }

    _fieldEl(name) {
        return document.querySelector(`.o_field_widget[name="${name}"]`) ||
            document.querySelector(`[name="${name}"].o_field_widget`) ||
            document.querySelector(`div[name="${name}"]`) ||
            document.querySelector(`field[name="${name}"]`);
    }

    _highlight(elements) {
        this._clearHighlight();
        const items = (Array.isArray(elements) ? elements : [elements]).filter(Boolean);
        items.forEach((el) => el.classList.add(HIGHLIGHT_CLASS));
        if (items[0]) {
            items[0].scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }

    async _focusGrantPortal() {
        // Open the Action/three-dot menu if it is not already open.
        let grant = [...document.querySelectorAll(".dropdown-item, .o-dropdown-item, a, button")]
            .find((el) => (el.textContent || "").trim().toLowerCase() === "grant portal access");
        if (!grant) {
            const buttons = [...document.querySelectorAll("button, a")];
            const actionBtn = buttons.find((el) => {
                const txt = (el.textContent || "").trim().toLowerCase();
                const title = (el.getAttribute("title") || "").toLowerCase();
                const aria = (el.getAttribute("aria-label") || "").toLowerCase();
                return txt === "action" || title.includes("action") || aria.includes("action");
            });
            if (actionBtn) {
                actionBtn.click();
                await new Promise((resolve) => setTimeout(resolve, 250));
            }
            grant = [...document.querySelectorAll(".dropdown-item, .o-dropdown-item, a, button")]
                .find((el) => (el.textContent || "").trim().toLowerCase() === "grant portal access");
        }
        if (grant) this._highlight(grant);
    }

    async _applyFocus() {
        this._clearHighlight();
        const focus = this.current?.focus;
        if (!focus) return;

        // Give the newly opened form time to render.
        await new Promise((resolve) => setTimeout(resolve, 450));

        if (focus === "grant_portal") {
            await this._focusGrantPortal();
            return;
        }

        if (focus === "related_user") {
            await this._clickTab("Settings");
            const el = await this._waitFor('.o_field_widget[name="user_id"]');
            this._highlight(el);
            return;
        }

        if (focus === "work_information") {
            await this._clickTab("Work Information");
            await new Promise((resolve) => setTimeout(resolve, 250));
            this._highlight([
                this._fieldEl("department_id"),
                this._fieldEl("parent_id"),
                this._fieldEl("work_location_ids"),
            ]);
            return;
        }

        if (focus === "work_location_header") {
            const el = document.querySelector(".o_form_sheet") || document.querySelector(".o_form_view");
            this._highlight(el);
            return;
        }

        if (focus === "project_geofence") {
            const el = this._fieldEl("project_line_ids") || [...document.querySelectorAll(".o_group")]
                .find((node) => (node.textContent || "").includes("Projects and Geolocation"));
            this._highlight(el);
            return;
        }

    }

    async _openCurrentTarget() {
        const step = this.current;
        if (!step || !step.target) {
            await this._applyFocus();
            return;
        }
        try {
            switch (step.target) {
                case "demo_contact": {
                    const id = await this._findOne("res.partner", ["|", ["email", "=", "employee1@eps-demo.local"], ["name", "=", "Demo Employee One"]]);
                    await this._openForm("res.partner", id, "Demo Employee Contact");
                    break;
                }
                case "demo_employee": {
                    const id = await this._findOne("hr.employee", ["|", ["user_id.login", "=", "employee1@eps-demo.local"], ["name", "=", "Demo Employee One"]]);
                    await this._openForm("hr.employee", id, "Demo Employee One");
                    break;
                }
                case "demo_work_location": {
                    const id = await this._findOne("hr.work.location", [["name", "=", "Demo Project Site"]]);
                    await this._openForm("hr.work.location", id, "Demo Project Site");
                    break;
                }
                case "roles_permissions":
                    await this.action.doAction("employee_portal_suite.action_employee_portal_suite_roles");
                    break;
                case "approval_roles":
                    await this.action.doAction("employee_portal_suite.action_employee_portal_approval_roles");
                    break;
                case "project_role_assignments":
                    await this.action.doAction("employee_portal_suite.action_employee_portal_project_role_assignments");
                    break;
                case "workflows":
                    await this.action.doAction("employee_portal_suite.action_employee_portal_workflows");
                    break;
                case "employee_requests":
                    await this.action.doAction("employee_portal_suite.action_employee_request");
                    break;
                case "material_requests":
                    await this.action.doAction("employee_portal_suite.action_material_request");
                    break;
            }
            await this._applyFocus();
        } catch (error) {
            this.notification.add("The tour could not open this screen automatically. You can continue with Next or open the screen manually.", { type: "warning" });
        }
    }

    async next() {
        if (this.state.step >= STEPS.length - 1) return;
        this._clearHighlight();
        this.state.step += 1;
        this._save();
        await this._openCurrentTarget();
    }

    async previous() {
        if (this.state.step <= 0) return;
        this._clearHighlight();
        this.state.step -= 1;
        this._save();
        await this._openCurrentTarget();
    }

    async reopenStep() {
        await this._openCurrentTarget();
    }

    openPortal() {
        window.open("/my/employee", "_blank", "noopener");
    }
}

registry.category("main_components").add(
    "employee_portal_suite.EPSDemoManagerTourOverlay",
    { Component: EPSDemoManagerTourOverlay },
    { sequence: 90 }
);
