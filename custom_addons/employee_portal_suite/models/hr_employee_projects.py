from odoo import api, fields, models, _


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Stored per employee. This field is intentionally not displayed directly
    # on the employee form; assignments are managed through a dedicated button.
    material_project_ids = fields.Many2many(
        "project.project",
        "hr_employee_material_project_rel",
        "employee_id",
        "project_id",
        string="Material Request Projects",
        help="Projects assigned only to this employee.",
    )
    material_project_count = fields.Integer(
        string="Assigned Projects",
        compute="_compute_material_project_count",
    )

    @api.depends("material_project_ids")
    def _compute_material_project_count(self):
        for employee in self:
            employee.material_project_count = len(employee.material_project_ids)

    @api.onchange("work_location_id")
    def _onchange_work_location_material_projects(self):
        """Keep only assignments available under the newly selected location.

        Never copy Work Location projects to the employee. An empty assignment
        remains empty and therefore gives the employee no Material Request
        projects until an authorized user assigns them explicitly.
        """
        for employee in self:
            allowed = (
                employee.work_location_id._get_material_request_projects()
                if employee.work_location_id
                else self.env["project.project"]
            )
            employee.material_project_ids = employee.material_project_ids & allowed

    def _get_material_request_projects(self):
        self.ensure_one()
        # No fallback to Work Location projects. This is the key separation:
        # employees at the same Work Location may have different assignments.
        return self.material_project_ids

    def action_manage_material_projects(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Assign Projects - %s") % self.name,
            "res_model": "hr.employee.project.assignment.wizard",
            "view_mode": "form",
            "view_id": self.env.ref(
                "employee_portal_suite.hr_employee_project_assignment_wizard_form"
            ).id,
            "target": "new",
            "context": {
                "default_employee_id": self.id,
                "active_id": self.id,
                "active_model": "hr.employee",
            },
        }


class HrEmployeeProjectAssignmentWizard(models.TransientModel):
    _name = "hr.employee.project.assignment.wizard"
    _description = "Assign Projects to Employee"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        readonly=True,
    )
    available_project_ids = fields.Many2many(
        "project.project",
        compute="_compute_available_project_ids",
        string="Available Projects",
    )
    project_ids = fields.Many2many(
        "project.project",
        "hr_employee_project_assignment_wizard_rel",
        "wizard_id",
        "project_id",
        string="Assigned Projects",
        domain="[('id', 'in', available_project_ids)]",
    )

    @api.depends(
        "employee_id",
        "employee_id.work_location_id",
        "employee_id.work_location_id.project_line_ids.project_id",
        "employee_id.work_location_id.project_id",
    )
    def _compute_available_project_ids(self):
        for wizard in self:
            wizard.available_project_ids = (
                wizard.employee_id.work_location_id._get_material_request_projects()
                if wizard.employee_id and wizard.employee_id.work_location_id
                else self.env["project.project"]
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        employee = self.env["hr.employee"].browse(
            values.get("employee_id") or self.env.context.get("active_id")
        )
        if employee.exists():
            values["employee_id"] = employee.id
            values["project_ids"] = [(6, 0, employee.material_project_ids.ids)]
        return values

    def action_apply(self):
        self.ensure_one()
        allowed = self.available_project_ids
        invalid = self.project_ids - allowed
        if invalid:
            from odoo.exceptions import ValidationError
            raise ValidationError(_("Only projects configured on the employee's Work Location can be assigned."))
        self.employee_id.material_project_ids = [(6, 0, self.project_ids.ids)]
        return {"type": "ir.actions.act_window_close"}
