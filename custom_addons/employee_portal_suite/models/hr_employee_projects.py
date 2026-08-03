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
        if not self.work_location_id:
            return self.env["project.project"]
        return self.work_location_id._get_material_request_projects(employee=self)

    def has_project_geofencing(self):
        self.ensure_one()
        if not self.work_location_id:
            return False
        return self.work_location_id.sudo().has_project_geofencing(employee=self)

    def check_employee_in_any_project_range(self, employee_lat, employee_lon):
        self.ensure_one()
        if not self.work_location_id:
            return True, None, None
        return self.work_location_id.sudo().check_employee_in_any_project_range(
            employee_lat, employee_lon, employee=self
        )
