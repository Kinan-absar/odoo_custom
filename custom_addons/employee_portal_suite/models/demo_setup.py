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

    def _safe_showcase_portal_group_ids(self, requested_groups):
        """Return a group set that is guaranteed to stay Portal-only.

        Some databases may carry older group metadata or implied groups from
        previous module revisions.  Odoo treats groups in the User Types
        category as mutually exclusive, so a custom group that directly or
        indirectly implies Internal User can make a Portal user invalid.

        Prefer cloning the already-working demo employee's exact group set when
        available.  Otherwise keep Portal plus only feature groups that do not
        belong to the User Types category and do not imply Internal/Public.
        """
        portal_group = self._group("base.group_portal")
        internal_group = self._group("base.group_user")
        public_group = self._group("base.group_public")
        user_type_category = self._group("base.module_category_user_type")
        if not portal_group:
            raise UserError(_("Portal user group could not be found."))

        # Best source of truth: an already-working portal demo user created by
        # the normal Prepare Demo flow.
        template = self.env["res.users"].sudo().search([
            ("login", "=", "employee1@eps-demo.local")
        ], limit=1)
        if template and portal_group in template.groups_id and internal_group not in template.groups_id:
            return template.groups_id.ids

        blocked_type_ids = {g.id for g in (internal_group, public_group) if g}
        safe_ids = [portal_group.id]
        for group in [g for g in requested_groups if g and g.id != portal_group.id]:
            # Never add another group explicitly classified as a User Type.
            if user_type_category and group.category_id.id == user_type_category.id:
                continue
            implied = group.trans_implied_ids if "trans_implied_ids" in group._fields else group.implied_ids
            if blocked_type_ids.intersection(implied.ids):
                continue
            safe_ids.append(group.id)
        return list(dict.fromkeys(safe_ids))

    def _get_or_create_portal_user(self, login, name, groups, password):
        """Create/refresh a showcase user with one atomic valid Portal group set.

        The previous implementation changed user types in several writes.  If a
        database already contained a partially configured showcase user, even a
        harmless write such as changing the name could trigger Odoo's
        "more than one user types" validation before the groups were repaired.
        This version computes the final valid groups first and applies everything
        in a single write/create operation.
        """
        Users = self.env["res.users"].sudo().with_context(no_reset_password=True)
        group_ids = self._safe_showcase_portal_group_ids(groups)
        vals = {
            "name": name,
            "login": login,
            "email": login,
            "active": True,
            "groups_id": [(6, 0, group_ids)],
        }
        user = Users.search([("login", "=", login)], limit=1)
        try:
            if user:
                user.write(vals)
            else:
                user = Users.create(vals)
            user.sudo().write({"password": password})
        except Exception as exc:
            raise UserError(_(
                "Could not prepare showcase portal user %(login)s. "
                "The final Portal-only group set could not be applied. Original error: %(error)s",
                login=login,
                error=str(exc),
            )) from exc
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
        manager_groups = [
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
        ]
        manager_user = self._get_or_create_user(
            "manager@eps-demo.local", "Demo Manager", manager_groups, password
        )
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


    def _showcase_department(self, name):
        Department = self.env["hr.department"].sudo()
        rec = Department.search([("name", "=", name), ("company_id", "in", [False, self.env.company.id])], limit=1)
        return rec or Department.create({"name": name, "company_id": self.env.company.id})

    def _showcase_project_location(self, project_name, location_name, street):
        company = self.env.company
        Project = self.env["project.project"].sudo()
        project = Project.search([("name", "=", project_name), ("company_id", "=", company.id)], limit=1)
        if not project:
            project = Project.create({"name": project_name, "company_id": company.id})
        Partner = self.env["res.partner"].sudo()
        address = Partner.search([("name", "=", location_name), ("type", "=", "other")], limit=1)
        if not address:
            address = Partner.create({"name": location_name, "type": "other", "company_id": company.id, "street": street, "city": "Riyadh"})
        Location = self.env["hr.work.location"].sudo()
        location = Location.search([("name", "=", location_name), ("company_id", "=", company.id)], limit=1)
        vals = {"name": location_name, "company_id": company.id, "address_id": address.id}
        if location:
            location.write(vals)
        else:
            location = Location.create(vals)
        Link = self.env["hr.work.location.project"].sudo()
        link = Link.search([("work_location_id", "=", location.id), ("project_id", "=", project.id)], limit=1)
        if not link:
            Link.create({"work_location_id": location.id, "project_id": project.id, "geo_enforce": False})
        return project, location

    def _prepare_showcase_dataset(self, password):
        """Create a rich, repeatable fictional dataset for screenshots and sales videos."""
        portal_groups = [
            self._group("base.group_portal"),
            self._group("employee_portal_suite.group_employee_portal"),
            self._group("employee_portal_suite.group_employee_portal_employee"),
            self._group("employee_portal_suite.group_portal_attendance_user"),
        ]
        departments = {name: self._showcase_department(name) for name in [
            "Management", "Projects", "HR & Administration", "Finance", "Procurement"
        ]}
        head_project, head_location = self._showcase_project_location("Head Office Operations", "Head Office - Riyadh", "King Fahd Road")
        health_project, health_location = self._showcase_project_location("Healthcare Center Fit-Out", "Healthcare Center Project", "Northern Ring Road")
        north_project, north_location = self._showcase_project_location("North Riyadh Office Fit-Out", "North Riyadh Project Site", "Olaya District")

        people = [
            ("Omar Khalid", "omar@eps-showcase.local", "Projects", health_location),
            ("Sara Ahmed", "sara@eps-showcase.local", "HR & Administration", head_location),
            ("Faisal Ali", "faisal@eps-showcase.local", "Finance", head_location),
            ("Mohammed Salem", "mohammed@eps-showcase.local", "Projects", north_location),
            ("Lina Hassan", "lina@eps-showcase.local", "Procurement", head_location),
            ("Yousef Nasser", "yousef@eps-showcase.local", "Projects", health_location),
            ("Maya Ibrahim", "maya@eps-showcase.local", "Projects", north_location),
            ("Adam Kareem", "adam@eps-showcase.local", "Projects", health_location),
        ]
        employees = {}
        for name, login, dept, location in people:
            user = self._get_or_create_portal_user(login, name, portal_groups, password)
            employees[name] = self._get_or_create_employee(name, user, departments[dept], work_location=location)

        # Make Omar the visible project lead for a realistic reporting hierarchy.
        for name in ["Yousef Nasser", "Adam Kareem"]:
            employees[name].sudo().write({"parent_id": employees["Omar Khalid"].id})
        employees["Maya Ibrahim"].sudo().write({"parent_id": employees["Mohammed Salem"].id})

        EmployeeRequest = self.env["employee.request"].sudo()
        request_rows = [
            ("Omar Khalid", "leave", "Annual leave - 5 working days", "approved"),
            ("Sara Ahmed", "travel", "Client workshop business trip", "manager"),
            ("Faisal Ali", "letter", "Salary certificate for bank", "hr"),
            ("Mohammed Salem", "asset", "Laptop and site tablet request", "finance"),
            ("Lina Hassan", "training", "Procurement negotiation workshop", "ceo"),
            ("Yousef Nasser", "advance", "Salary advance request", "approved"),
            ("Maya Ibrahim", "medical", "Medical reimbursement claim", "rejected"),
        ]
        for emp_name, req_type, desc, state in request_rows:
            emp = employees[emp_name]
            rec = EmployeeRequest.search([("employee_id", "=", emp.id), ("description", "=", desc)], limit=1)
            vals = {"employee_id": emp.id, "request_type": req_type, "description": desc, "state": state}
            rec.write(vals) if rec else EmployeeRequest.create(vals)

        MaterialRequest = self.env["material.request"].sudo()
        material_sets = [
            ("Omar Khalid", health_project, health_location, "purchase", [("LED Panel Light 60x60", 24), ("Electrical Cable 4mm", 300), ("PVC Conduit 25mm", 120)]),
            ("Mohammed Salem", north_project, north_location, "project_manager", [("Gypsum Board 12.5mm", 80), ("Metal Stud 70mm", 150)]),
            ("Yousef Nasser", health_project, health_location, "approved", [("Fire Rated Sealant", 30), ("Cable Tray 150mm", 45)]),
        ]
        valid_states = dict(MaterialRequest._fields["state"].selection) if isinstance(MaterialRequest._fields["state"].selection, list) else {}
        for emp_name, project, location, desired_state, lines in material_sets:
            emp = employees[emp_name]
            worksite = location.name
            mr = MaterialRequest.search([("employee_id", "=", emp.id), ("worksite", "=", worksite)], limit=1)
            state = desired_state if desired_state in valid_states else "draft"
            vals = {"employee_id": emp.id, "worksite": worksite, "project_id": project.id, "work_location_id": location.id, "state": state}
            if mr:
                mr.write(vals)
            else:
                mr = MaterialRequest.create(vals)
            if not mr.line_ids:
                self.env["material.request.line"].sudo().create([{"request_id": mr.id, "item_name": item, "qty_required": qty} for item, qty in lines])

        Attendance = self.env["hr.attendance"].sudo()
        now = fields.Datetime.now()
        showcase_employees = list(employees.values())
        for day in range(1, 6):
            for idx, emp in enumerate(showcase_employees):
                check_in = (now - timedelta(days=day)).replace(hour=8, minute=(idx * 3) % 25, second=0, microsecond=0)
                check_out = check_in + timedelta(hours=8, minutes=20 + (idx % 4) * 10)
                existing = Attendance.search([("employee_id", "=", emp.id), ("check_in", "=", check_in)], limit=1)
                if not existing:
                    vals = {"employee_id": emp.id, "check_in": check_in, "check_out": check_out}
                    location = emp.work_location_id
                    project = health_project if location == health_location else north_project if location == north_location else head_project
                    if "check_in_project_id" in Attendance._fields:
                        vals["check_in_project_id"] = project.id
                    if "check_in_work_location_id" in Attendance._fields:
                        vals["check_in_work_location_id"] = location.id
                    Attendance.create(vals)

        Announcement = self.env["portal.announcement"].sudo()
        announcements = [
            ("Employee Portal 2.0 is Live", "<p>Requests, attendance, approvals and team communication are now available from one employee workspace.</p>", "success", 120),
            ("Monthly Safety Meeting", "<p>Project teams: monthly safety meeting is scheduled for Thursday at 9:00 AM.</p>", "warning", 110),
            ("September Payroll Notice", "<p>September payroll processing is in progress. Salary reports will be available through the portal.</p>", "primary", 100),
            ("Healthcare Center Project Update", "<p>Great progress this week. Please keep material requests and attendance updated daily.</p>", "primary", 90),
        ]
        for name, message, color, sequence in announcements:
            rec = Announcement.search([("name", "=", name)], limit=1)
            vals = {"name": name, "message": message, "target": "both", "active": True, "color": color, "sequence": sequence}
            rec.write(vals) if rec else Announcement.create(vals)

        # Small real PDF documents make the Reports area visibly populated.
        import base64
        pdf = base64.b64encode(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")
        Report = self.env["portal.report.document"].sudo()
        report_group = self._group("employee_portal_suite.group_employee_portal")
        for title, filename, description in [
            ("September Project Progress Summary", "September_Project_Progress.pdf", "Monthly progress summary for project teams."),
            ("Employee Portal Quick Guide", "Employee_Portal_Quick_Guide.pdf", "Quick reference for employee self-service features."),
            ("Health & Safety Bulletin", "Health_and_Safety_Bulletin.pdf", "Latest site health and safety bulletin."),
        ]:
            rec = Report.search([("name", "=", title)], limit=1)
            vals = {"name": title, "description": description, "date": fields.Date.context_today(self), "active": True, "file": pdf, "filename": filename, "company_id": self.env.company.id}
            if report_group:
                vals["allowed_group_ids"] = [(6, 0, [report_group.id])]
            rec.write(vals) if rec else Report.create(vals)

        return employees

    def action_prepare_showcase_demo(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise UserError(_("Only an Odoo administrator can prepare the showcase environment."))
        if not self.confirm_disposable:
            raise UserError(_("Confirm that this is a disposable demo/development database before continuing."))
        password = self.demo_password or "Demo123!"
        # Showcase preparation is independent from the lightweight guided-tour demo.
        # Do not recreate or modify the existing demo manager/employee accounts here;
        # if they already exist, they remain untouched and both demo modes can coexist.
        employees = self._prepare_showcase_dataset(password)
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url", "").rstrip("/")
        self.result_html = _("""
            <div class="alert alert-success" role="alert">
                <h4>Showcase demo is ready for recording.</h4>
                <p>A realistic fictional company dataset was created: departments, projects, work locations, 8 showcase employees, mixed employee requests, material requests, five days of attendance, announcements and portal reports.</p>
            </div>
            <p><strong>Recommended video employee:</strong> Omar Khalid — <code>omar@eps-showcase.local</code> — password <code>%s</code></p>
            <p><strong>Other showcase users:</strong> Sara, Faisal, Mohammed, Lina, Yousef, Maya and Adam all use the same demo password.</p>
            <p><strong>Guided-tour accounts are untouched:</strong> if <code>employee1@eps-demo.local</code>, <code>employee2@eps-demo.local</code> and <code>manager@eps-demo.local</code> already exist, Showcase preparation leaves them exactly as they are.</p>
            <p><a class="btn btn-primary" href="%s/my/employee" target="_blank">Open Employee Portal</a> <a class="btn btn-secondary" href="%s/web" target="_blank">Open Backend</a></p>
        """) % (password, base_url, base_url)
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new"}

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
            <p><strong>Suggested demo:</strong> log in as Employee 1, submit a request, then open an incognito/private window as Manager and approve it. Also try Material Requests, Attendance and Discuss.</p>
        """) % (password, backend_url, password, portal_url, password, portal_url)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
