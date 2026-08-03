from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Retained as a hidden compatibility field because earlier releases created
    # this relation. It is no longer used for Material Request routing.
    material_project_ids = fields.Many2many(
        "project.project",
        "hr_employee_material_project_rel",
        "employee_id",
        "project_id",
        string="Deprecated Assigned Projects",
    )

    def _get_material_request_projects(self):
        self.ensure_one()
        if self.work_location_id:
            return self.work_location_id._get_material_request_projects()
        return self.env["project.project"]
