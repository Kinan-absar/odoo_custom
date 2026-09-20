# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class EmployeePortalDemoSetup(models.TransientModel):
    _name = "employee.portal.demo.setup"
    _description = "Employee Portal Suite Demo Setup"

    demo_password = fields.Char(
        string="Demo Password",
        default="Demo123!",
        required=True,
        help="This password is applied to all demo users every time the setup is prepared.",
    )
    confirm_disposable = fields.Boolean(
        string="I confirm this is a disposable demo/development database",
        help="The setup creates fictional users and sample business records. Run it only on a disposable demo/dev database.",
    )
    result_html = fields.Html(string="Demo Access", readonly=True, sanitize=False)

    def _group(self, xmlid):
        return self.env.ref(xmlid, raise_if_not_found=False)

    def _get_or_create_user(self, login, name, groups, password):
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        user = Users.search([("login", "=", login)], limit=1)
        group_ids = [group.id for group in groups if group]
        vals = {
            "name": name,
            "login": login,
            "email": login,
            "active": True,
            "groups_id": [(6, 0, group_ids)],
        }
        if user:
            user.write(vals)
        else:
            user = Users.create(vals)
        user.sudo().write({"password": password})
        return user

    def _get_or_create_employee(self, name, user, department, manager=False, work_location=False):
        Employee = self.env["hr.employee"].sudo()
        employee = Employee.search([("user_id", "=", user.id)], limit=1)
        vals = {
            "name": name,
            "user_id": user.id,
            "company_id": self.env.company.id,
            "department_id": department.id,
            "parent_id": manager.id if manager else False,
        }
        if work_location:
            vals.update({
                "work_location_id": work_location.id,
                "work_location_ids": [(6, 0, [work_location.id])],
            })
        if employee:
            employee.write(vals)
        else:
            employee = Employee.create(vals)
        return employee

    def _prepare_master_data(self):
        company = self.env.company
        Department = self.env["hr.department"].sudo()
        department = Department.search([
            ("name", "=", "Demo Operations"),
            ("company_id", "in", [False, company.id]),
        ], limit=1)
        if not department:
            department = Department.create({"name": "Demo Operations", "company_id": company.id})

        Project = self.env["project.project"].sudo()
        project = Project.search([("name", "=", "Demo Office Fit-Out"), ("company_id", "=", company.id)], limit=1)
        if not project:
            project = Project.create({"name": "Demo Office Fit-Out", "company_id": company.id})

        # Odoo 18 requires every Work Location to have a Work Address (address_id).
        # Reuse a dedicated fictional partner so the demo remains self-contained.
        Partner = self.env["res.partner"].sudo()
        demo_address = Partner.search([
            ("name", "=", "Demo Project Site"),
            ("company_id", "in", [False, company.id]),
            ("type", "=", "other"),
        ], limit=1)
        if not demo_address:
            demo_address = Partner.create({
                "name": "Demo Project Site",
                "type": "other",
                "company_id": company.id,
                "street": "100 Demo Avenue",
                "city": "Demo City",
            })

        WorkLocation = self.env["hr.work.location"].sudo()
        location = WorkLocation.search([("name", "=", "Demo Project Site"), ("company_id", "=", company.id)], limit=1)
        location_vals = {
            "name": "Demo Project Site",
            "company_id": company.id,
            "address_id": demo_address.id,
        }
        if location:
            location.write(location_vals)
        else:
            location = WorkLocation.create(location_vals)

        LocationProject = self.env["hr.work.location.project"].sudo()
        link = LocationProject.search([
            ("work_location_id", "=", location.id),
            ("project_id", "=", project.id),
        ], limit=1)
        if not link:
            LocationProject.create({
                "work_location_id": location.id,
                "project_id": project.id,
                "geo_enforce": False,
            })
        return department, project, location

    def _prepare_users_and_employees(self, password, department, location):
        portal_common = [
            self._group("base.group_portal"),
            self._group("employee_portal_suite.group_employee_portal"),
            self._group("employee_portal_suite.group_employee_portal_employee"),
            self._group("employee_portal_suite.group_portal_attendance_user"),
        ]
        # This is a disposable demo environment. Clone the access groups of the
        # administrator who runs Demo Setup, then add all EPS-specific demo roles.
        # This is deliberately broad so the demo manager can explore backend
        # workflows without hitting unrelated Odoo access-right errors.
        manager_groups = list(self.env.user.groups_id) + [
            self._group("base.group_user"),
            self._group("employee_portal_suite.group_employee_portal_manager"),
            self._group("employee_portal_suite.group_employee_portal_hr"),
            self._group("employee_portal_suite.group_employee_portal_finance"),
            self._group("employee_portal_suite.group_employee_portal_ceo"),
            self._group("employee_portal_suite.group_employee_portal_admin"),
            self._group("employee_portal_suite.group_employee_portal_announcement_manager"),
            self._group("employee_portal_suite.group_salary_report_viewer"),
            self._group("employee_portal_suite.group_portal_report_uploader"),
            self._group("employee_portal_suite.group_mr_purchase_rep"),
            self._group("employee_portal_suite.group_mr_store_manager"),
            self._group("employee_portal_suite.group_mr_project_manager"),
            self._group("employee_portal_suite.group_mr_projects_director"),
            # Material Request backend views can reference vendor bills / journal entries.
            # Odoo grants the necessary read access to Purchase users without making
            # the demo manager an Accounting Administrator.
            self._group("purchase.group_purchase_user"),
            # Some EPS backend views/read paths dereference account.move fields.
            # Give the demo manager Accounting Read-only access so those records
            # can be displayed without granting invoicing or administrator rights.
            self._group("account.group_account_readonly"),
            # This is a disposable public demo manager. Give it broad backend
            # access so prospects can freely explore workflows without hitting
            # access errors while testing the module.
            self._group("base.group_system"),
            self._group("account.group_account_manager"),
            self._group("account.group_account_invoice"),
            self._group("purchase.group_purchase_manager"),
            self._group("hr.group_hr_manager"),
            self._group("hr_attendance.group_hr_attendance_manager"),
            self._group("project.group_project_manager"),
        ]
        manager_user = self._get_or_create_user(
            "manager@eps-demo.local", "Demo Manager", manager_groups, password
        )
        # Mirror the preparer's company access as well. In a disposable demo,
        # the manager should be able to open anything the setup administrator can.
        manager_user.sudo().write({
            "company_id": self.env.company.id,
            "company_ids": [(6, 0, self.env.user.company_ids.ids)],
        })
        employee1_user = self._get_or_create_user(
            "employee1@eps-demo.local", "Demo Employee One", portal_common, password
        )
        employee2_user = self._get_or_create_user(
            "employee2@eps-demo.local", "Demo Employee Two", portal_common, password
        )

        manager = self._get_or_create_employee(
            "Demo Manager", manager_user, department, work_location=location
        )
        employee1 = self._get_or_create_employee(
            "Demo Employee One", employee1_user, department, manager=manager, work_location=location
        )
        employee2 = self._get_or_create_employee(
            "Demo Employee Two", employee2_user, department, manager=manager, work_location=location
        )
        return manager_user, employee1_user, employee2_user, manager, employee1, employee2

    def _prepare_sample_records(self, manager, employee1, employee2, project, location):
        EmployeeRequest = self.env["employee.request"].sudo()
        demo_requests = [
            (employee1, "leave", "Annual leave request for five working days.", "manager"),
            (employee1, "advance", "Salary advance request for demonstration purposes.", "finance"),
            (employee2, "training", "Training course approval request.", "approved"),
        ]
        for employee, request_type, description, state in demo_requests:
            existing = EmployeeRequest.search([
                ("employee_id", "=", employee.id),
                ("description", "=", description),
            ], limit=1)
            vals = {
                "employee_id": employee.id,
                "request_type": request_type,
                "description": description,
                "state": state,
            }
            if existing:
                existing.write(vals)
            else:
                EmployeeRequest.create(vals)

        MaterialRequest = self.env["material.request"].sudo()
        material_description = "Demo Project Site"
        mr = MaterialRequest.search([
            ("employee_id", "=", employee1.id),
            ("worksite", "=", material_description),
        ], limit=1)
        mr_vals = {
            "employee_id": employee1.id,
            "worksite": material_description,
            "project_id": project.id,
            "work_location_id": location.id,
            "state": "purchase",
        }
        if mr:
            mr.write(mr_vals)
        else:
            mr = MaterialRequest.create(mr_vals)
        if not mr.line_ids:
            self.env["material.request.line"].sudo().create([
                {"request_id": mr.id, "item_name": "LED Panel Light 60x60", "qty_required": 12.0},
                {"request_id": mr.id, "item_name": "Electrical Cable 4mm", "qty_required": 200.0},
            ])

        Attendance = self.env["hr.attendance"].sudo()
        now = fields.Datetime.now()
        for idx, employee in enumerate((employee1, employee2), start=1):
            check_in = now - timedelta(days=idx, hours=8)
            check_out = now - timedelta(days=idx)
            existing = Attendance.search([
                ("employee_id", "=", employee.id),
                ("check_in", "=", check_in),
            ], limit=1)
            if not existing:
                vals = {"employee_id": employee.id, "check_in": check_in, "check_out": check_out}
                # Custom project/location fields are optional across revisions.
                if "project_id" in Attendance._fields:
                    vals["project_id"] = project.id
                if "work_location_id" in Attendance._fields:
                    vals["work_location_id"] = location.id
                Attendance.create(vals)

        Announcement = self.env["portal.announcement"].sudo()
        ann = Announcement.search([("name", "=", "Welcome to the Employee Portal Suite Demo")], limit=1)
        ann_vals = {
            "name": "Welcome to the Employee Portal Suite Demo",
            "message": (
                "<p>This is a prepared demonstration environment. Try employee requests, "
                "material requests, attendance, approvals, messaging and the employee portal.</p>"
            ),
            "target": "both",
            "active": True,
            "color": "primary",
            "sequence": 100,
        }
        if ann:
            ann.write(ann_vals)
        else:
            Announcement.create(ann_vals)

        # Configure project approvers so the material-request workflow can be tested.
        project.sudo().write({
            "store_manager_employee_id": manager.id,
            "project_manager_employee_id": manager.id,
        })

    def action_prepare_demo(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an Odoo administrator can prepare the demo environment."))
        if not self.confirm_disposable:
            raise UserError(_("Confirm that this is a disposable demo/development database before continuing."))

        password = self.demo_password or "Demo123!"
        department, project, location = self._prepare_master_data()
        manager_user, employee1_user, employee2_user, manager, employee1, employee2 = (
            self._prepare_users_and_employees(password, department, location)
        )
        self._prepare_sample_records(manager, employee1, employee2, project, location)

        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "")
        portal_url = "%s/my/employee" % base_url.rstrip("/") if base_url else "/my/employee"
        backend_url = "%s/web" % base_url.rstrip("/") if base_url else "/web"
        self.result_html = _("""
            <div class="alert alert-success" role="alert">
                <h4>Employee Portal Suite demo is ready.</h4>
                <p>The setup is safe to run again; it refreshes the same demo users and sample records.</p>
            </div>
            <table class="table table-sm table-bordered">
                <thead><tr><th>Role</th><th>Login</th><th>Password</th><th>Start here</th></tr></thead>
                <tbody>
                    <tr><td>Manager / Approver</td><td>manager@eps-demo.local</td><td>%s</td><td><a href="%s" target="_blank">Backend</a></td></tr>
                    <tr><td>Portal Employee 1</td><td>employee1@eps-demo.local</td><td>%s</td><td><a href="%s" target="_blank">Employee Portal</a></td></tr>
                    <tr><td>Portal Employee 2</td><td>employee2@eps-demo.local</td><td>%s</td><td><a href="%s" target="_blank">Employee Portal</a></td></tr>
                </tbody>
            </table>
            <div class="alert alert-info mt-3"><strong>Recommended customer journey</strong><ol class="mb-0 mt-2"><li>Start as <strong>Portal Employee 1</strong> and follow the Live Demo guide on the dashboard.</li><li>Submit an Employee Request and a Material Request, then try Attendance and Discuss.</li><li>Open an incognito/private window as <strong>Manager</strong> and review/approve the same records in the backend.</li><li>Return to Employee 1 to see the updated statuses and notifications.</li><li>Use Employee 2 for messaging, calls and employee-isolation testing.</li></ol></div>
        """) % (password, backend_url, password, portal_url, password, portal_url)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
