from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Existing relation retained from earlier releases. It is now the employee-
    # specific assignment used by Material Requests and attendance geofencing.
    material_project_ids = fields.Many2many(
        "project.project",
        "hr_employee_material_project_rel",
        "employee_id",
        "project_id",
        string="Projects",
        domain="[('id', 'in', available_work_location_project_ids)]",
        help="Projects assigned specifically to this employee. Other employees at the same work location are not affected.",
    )

    available_work_location_project_ids = fields.Many2many(
        "project.project",
        string="Available Work Location Projects",
        compute="_compute_available_work_location_project_ids",
    )

    @api.depends(
        "work_location_id",
        "work_location_id.project_line_ids.project_id",
        "work_location_id.project_id",
    )
    def _compute_available_work_location_project_ids(self):
        for employee in self:
            employee.available_work_location_project_ids = (
                employee.work_location_id._get_material_request_projects()
                if employee.work_location_id
                else self.env["project.project"]
            )

    @api.onchange("work_location_id")
    def _onchange_work_location_material_projects(self):
        for employee in self:
            allowed = employee.available_work_location_project_ids
            employee.material_project_ids = employee.material_project_ids & allowed

    def _get_material_request_projects(self):
        self.ensure_one()
        # Employee-specific assignments take priority. For existing employees
        # not configured yet, preserve the former work-location behavior.
        if self.material_project_ids:
            return self.material_project_ids
        if self.work_location_id:
            return self.work_location_id._get_material_request_projects()
        return self.env["project.project"]
