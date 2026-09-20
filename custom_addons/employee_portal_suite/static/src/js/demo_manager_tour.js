/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY = "eps_demo_manager_tour";

const STEPS = [
    {
        title: "Welcome to Employee Portal Suite",
        text: "This guided setup tour shows the complete manager/admin setup: portal access, employee linking, work location, project setup, approvals, and finally the employee experience.",
    },
    {
        title: "1. Start from Contacts",
        text: "Every portal employee starts as a Contact. This is where you create or open the employee's contact record before giving portal access.",
        target: "contacts",
    },
    {
        title: "2. Grant Portal Access",
        text: "The demo employee Contact is opened for you. Use Action > Grant Portal Access. Enter the employee email and grant access. This creates a portal user and sends the invitation. Portal users are external users and do not consume an internal-user seat.",
        target: "demo_contact",
    },
    {
        title: "3. Open the matching Employee",
        text: "Now move to Employees. The HR employee record holds the manager, department, work location and the user relationship used by Employee Portal Suite.",
        target: "demo_employee",
    },
    {
        title: "4. Link the Related User",
        text: "On the Employee, open HR Settings and set Related User to the portal user created from the Contact. This link is essential: it tells Employee Portal Suite which employee belongs to the logged-in portal account.",
        target: "demo_employee",
    },
    {
        title: "5. Manager, Department & Work Location",
        text: "On the same Employee record, assign the Manager, Department and Work Location. These relationships drive visibility, approvals, attendance and project/site behavior.",
        target: "demo_employee",
    },
    {
        title: "6. Configure the Work Location",
        text: "Every portal employee should have a Work Location. The demo Work Location is opened for you. It has a Work Address and can contain one or more project/geofence definitions.",
        target: "demo_work_location",
    },
    {
        title: "7. Link the Project / Geofence",
        text: "Inside the Work Location, use Projects and Geolocation to link the relevant Project. Latitude, longitude and radius can be used when attendance geofencing is required.",
        target: "demo_work_location",
    },
    {
        title: "8. Configure Project Approvers",
        text: "The demo Project is opened for you. Set the project-specific responsible employees/users used by Material Requests, such as Store Manager and Project Manager. Other approval roles are controlled by Employee Portal Suite security groups.",
        target: "demo_project",
    },
    {
        title: "9. Review Approval Workflows",
        text: "Employee Requests follow the Manager / HR / Finance / CEO flow. Material Requests can move through Purchase, Store, Project Manager, Director and CEO. Open the request area and review the records created by the demo setup.",
        target: "employee_requests",
    },
    {
        title: "10. Experience the Employee Portal",
        text: "Setup is complete. Open the Employee Portal in a new tab and log in as employee1@eps-demo.local. Try requests, material requests, attendance, reports, announcements, messaging, calls and notifications, then return as Manager to approve what the employee submitted.",
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
            await this._computeVisibility();
            if (!this.state.visible) {
                return;
            }
            const saved = window.localStorage.getItem(STORAGE_KEY);
            if (saved) {
                try {
                    const data = JSON.parse(saved);
                    this.state.active = Boolean(data.active);
                    const step = Number(data.step);
                    this.state.step = Number.isFinite(step)
                        ? Math.max(0, Math.min(step, STEPS.length - 1))
                        : 0;
                } catch (_) {
                    window.localStorage.removeItem(STORAGE_KEY);
                }
            }
        });
    }

    async _computeVisibility() {
        try {
            const demoUsers = await this.orm.searchRead(
                "res.users",
                [["login", "=", "manager@eps-demo.local"]],
                ["id"],
                { limit: 1 }
            );
            this.state.visible = Boolean(demoUsers.length);
        } catch (_) {
            // Never break the Odoo backend because the optional demo widget
            // could not check its demo user.
            this.state.visible = false;
        }
    }

    get current() {
        return STEPS[this.state.step];
    }

    get total() {
        return STEPS.length;
    }

    _save() {
        window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({ active: this.state.active, step: this.state.step })
        );
    }

    start() {
        this.state.active = true;
        if (!Number.isFinite(this.state.step)) {
            this.state.step = 0;
        }
        this._save();
    }

    collapse() {
        this.state.active = false;
        this._save();
    }

    restart() {
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
            this.notification.add(`${name} was not found. Run Prepare / Reset Demo first.`, {
                type: "warning",
            });
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

    async _openCurrentTarget() {
        const step = this.current;
        if (!step || !step.target) {
            return;
        }
        try {
            switch (step.target) {
                case "contacts":
                    await this.action.doAction("base.action_partner_form");
                    break;
                case "demo_contact": {
                    const id = await this._findOne("res.partner", [
                        "|",
                        ["email", "=", "employee1@eps-demo.local"],
                        ["name", "=", "Demo Employee One"],
                    ]);
                    await this._openForm("res.partner", id, "Demo Employee Contact");
                    break;
                }
                case "demo_employee": {
                    const id = await this._findOne("hr.employee", [
                        ["user_id.login", "=", "employee1@eps-demo.local"],
                    ]);
                    await this._openForm("hr.employee", id, "Demo Employee One");
                    break;
                }
                case "demo_work_location": {
                    const id = await this._findOne("hr.work.location", [
                        ["name", "=", "Demo Project Site"],
                    ]);
                    await this._openForm("hr.work.location", id, "Demo Project Site");
                    break;
                }
                case "demo_project": {
                    const id = await this._findOne("project.project", [
                        ["name", "=", "Demo Office Fit-Out"],
                    ]);
                    await this._openForm("project.project", id, "Demo Office Fit-Out");
                    break;
                }
                case "employee_requests":
                    await this.action.doAction("employee_portal_suite.action_employee_request");
                    break;
            }
        } catch (error) {
            this.notification.add(
                "The tour could not open this screen automatically. You can continue with Next or open the screen manually.",
                { type: "warning" }
            );
        }
    }

    async next() {
        if (this.state.step >= STEPS.length - 1) {
            return;
        }
        this.state.step += 1;
        this._save();
        await this._openCurrentTarget();
    }

    async previous() {
        if (this.state.step <= 0) {
            return;
        }
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
