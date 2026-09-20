/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const STEPS = [
    {title: "Welcome to Employee Portal Suite", text: "This guided setup tour shows how an administrator onboards a free portal employee and configures the employee, work location, project, approvals, and employee experience.", action: null},
    {title: "1. Create the employee Contact", text: "Portal employees start as Contacts. Create/open the employee contact here. The contact is the identity that will receive portal access.", action: "base.action_partner_form"},
    {title: "2. Grant Portal Access", text: "Open the employee Contact, then use Action > Grant Portal Access. Enter the employee email and grant access. Odoo sends the portal invitation. Portal users are external users and do not consume an internal-user seat.", action: "base.action_partner_form"},
    {title: "3. Create or open the Employee", text: "Now open Employees and create/open the matching employee record. This holds the HR, manager, department, work-location and portal relationship used by Employee Portal Suite.", action: "hr.open_view_employee_list_my"},
    {title: "4. Link the Related User", text: "On the Employee, open the HR Settings tab and set Related User to the portal user created from the Contact. This link is essential: it tells the portal which employee belongs to the logged-in portal account.", action: "hr.open_view_employee_list_my"},
    {title: "5. Assign Manager, Department & Work Location", text: "On the Employee record, set the Manager, Department and Work Location. Employee Portal Suite uses these relationships for visibility, approvals, attendance and project/site behavior.", action: "hr.open_view_employee_list_my"},
    {title: "6. Configure the Work Location", text: "Open Work Locations. Every portal employee should have a work location. The work location also has a Work Address and can contain one or more project/geofence definitions.", action: "hr.hr_work_location_action"},
    {title: "7. Add the Project to the Work Location", text: "Inside the Work Location, use Projects and Geolocation to add the relevant Project. You can optionally enforce latitude, longitude and radius for project attendance geofencing.", action: "hr.hr_work_location_action"},
    {title: "8. Configure the Project & Approvers", text: "Open Projects and check the project-specific responsible employees/users used by Material Requests, such as Store Manager and Project Manager. Other approval roles are controlled by Employee Portal Suite security groups.", action: "project.open_view_project_all"},
    {title: "9. Review Employee & Material Workflows", text: "Employee Requests use the Manager/HR/Finance/CEO flow, while Material Requests can move through Purchase, Store, Project Manager, Director and CEO. Open the Employee Portal app to review and approve requests.", action: "employee_portal_suite.action_employee_request"},
    {title: "10. Experience the Employee Portal", text: "The setup is complete. Log in with employee1@eps-demo.local to experience /my/employee: requests, material requests, attendance, reports, announcements, messaging, calls and notifications. Then return as Manager to approve what the employee submitted.", action: null, url: "/my/employee"},
];

export class EPSDemoManagerTour extends Component {
    static template = "employee_portal_suite.EPSDemoManagerTour";
    setup() {
        this.action = useService("action");
        this.state = useState({step: 0});
    }
    get current() { return STEPS[this.state.step]; }
    get total() { return STEPS.length; }
    async _showStep(index) {
        this.state.step = Math.max(0, Math.min(index, STEPS.length - 1));
        const step = this.current;
        if (step.action) {
            try { await this.action.doAction(step.action); } catch (e) { /* keep guide open if an optional action is unavailable */ }
        }
    }
    next() {
        if (this.state.step >= STEPS.length - 1) return;
        this._showStep(this.state.step + 1);
    }
    previous() { this._showStep(this.state.step - 1); }
    openPortal() { window.open("/my/employee", "_blank"); }
}
registry.category("actions").add("eps_demo_manager_tour", EPSDemoManagerTour);
