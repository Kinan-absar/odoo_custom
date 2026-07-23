from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    material_project_ids = fields.Many2many(
        "project.project",
        "hr_employee_material_project_rel",
        "employee_id",
        "project_id",
        string="Assigned Projects",
        help=(
            "Projects this employee may use when creating Material Requests. "
            "When empty, the project linked to the employee's work location is used "
            "for backward compatibility."
        ),
    )

    def _get_material_request_projects(self):
        self.ensure_one()
        if self.material_project_ids:
            return self.material_project_ids
        if self.work_location_id and self.work_location_id.project_id:
            return self.work_location_id.project_id
        return self.env["project.project"]
