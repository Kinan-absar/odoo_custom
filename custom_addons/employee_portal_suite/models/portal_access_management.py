from odoo import api, fields, models, _


class EmployeePortalAccessRole(models.Model):
    _name = "employee.portal.access.role"
    _description = "Employee Portal Access Role"
    _order = "section, sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    section = fields.Selection(
        [
            ("feature", "Portal Feature Access"),
            ("approval", "Global Approval Role"),
            ("admin", "Administration / Reporting"),
            ("other", "Other Installed Module"),
        ],
        required=True,
        default="feature",
    )
    group_id = fields.Many2one(
        "res.groups",
        string="Underlying Odoo Group",
        required=True,
        ondelete="cascade",
        help="The technical Odoo group synchronized by this friendly access screen.",
    )
    user_ids = fields.Many2many(
        "res.users",
        string="Users",
        compute="_compute_user_ids",
        inverse="_inverse_user_ids",
        compute_sudo=True,
        help="Choose all users who should receive this access or role.",
    )
    user_count = fields.Integer(compute="_compute_user_count")
    notes = fields.Text()

    _sql_constraints = [
        ("employee_portal_access_role_group_unique", "unique(group_id)", "This Odoo group is already managed here."),
    ]

    @api.depends("group_id", "group_id.users")
    def _compute_user_ids(self):
        for rec in self:
            rec.user_ids = rec.group_id.sudo().users if rec.group_id else False

    def _inverse_user_ids(self):
        for rec in self:
            if rec.group_id:
                rec.group_id.sudo().write({"users": [(6, 0, rec.user_ids.ids)]})

    @api.depends("user_ids")
    def _compute_user_count(self):
        for rec in self:
            rec.user_count = len(rec.user_ids)

    def action_select_all_portal_users(self):
        portal_group = self.env.ref("base.group_portal", raise_if_not_found=False)
        users = portal_group.sudo().users.filtered(lambda u: u.active and not u.share is False) if portal_group else self.env["res.users"]
        # base.group_portal users are share users. Keep the filter explicit and simple.
        if portal_group:
            users = portal_group.sudo().users.filtered("active")
        for rec in self:
            rec.user_ids = [(6, 0, users.ids)]
        return True

    def action_select_all_employee_users(self):
        employees = self.env["hr.employee"].sudo().search([("user_id", "!=", False), ("active", "=", True)])
        users = employees.mapped("user_id").filtered("active")
        for rec in self:
            rec.user_ids = [(6, 0, users.ids)]
        return True

    def action_clear_users(self):
        for rec in self:
            rec.user_ids = [(5, 0, 0)]
        return True


class ProjectProject(models.Model):
    _inherit = "project.project"

    def _sync_eps_project_role_groups(self):
        """Keep project-scoped Material Request roles out of Settings.

        Store Manager and Project Manager are selected on the project. Their
        related users are automatically synchronized to the technical groups
        required by the existing portal controllers/ACLs.
        """
        Project = self.sudo().with_context(active_test=False)
        mappings = [
            ("store_manager_employee_id", "employee_portal_suite.group_mr_store_manager"),
            ("project_manager_employee_id", "employee_portal_suite.group_mr_project_manager"),
        ]
        for field_name, group_xmlid in mappings:
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
            if not group:
                continue
            assigned_users = Project.search([(field_name, "!=", False)]).mapped(field_name).mapped("user_id").filtered("active")
            group.sudo().write({"users": [(6, 0, assigned_users.ids)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if any(vals.get("store_manager_employee_id") or vals.get("project_manager_employee_id") for vals in vals_list):
            records._sync_eps_project_role_groups()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "store_manager_employee_id" in vals or "project_manager_employee_id" in vals:
            self._sync_eps_project_role_groups()
        return result

    def unlink(self):
        had_roles = bool(self.filtered(lambda p: p.store_manager_employee_id or p.project_manager_employee_id))
        result = super().unlink()
        if had_roles:
            self.env["project.project"]._sync_eps_project_role_groups()
        return result
