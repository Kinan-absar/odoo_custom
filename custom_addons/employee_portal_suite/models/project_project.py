from odoo import models, fields, api

class ProjectProject(models.Model):
    _inherit = "project.project"

    # --- RESPONSIBLE EMPLOYEES ---
    store_manager_employee_id = fields.Many2one(
        "hr.employee",
        string="Store Manager"
    )

    project_manager_employee_id = fields.Many2one(
        "hr.employee",
        string="Project Manager"
    )

    # --- DERIVED USERS (SAFE FOR PORTAL USERS) ---
    store_manager_user_id = fields.Many2one(
        "res.users",
        compute="_compute_responsible_users",
        store=True
    )

    project_manager_user_id = fields.Many2one(
        "res.users",
        compute="_compute_responsible_users",
        store=True
    )

    @api.depends(
        "store_manager_employee_id",
        "project_manager_employee_id"
    )
    def _compute_responsible_users(self):
        for project in self:
            project.store_manager_user_id = project.store_manager_employee_id.user_id
            project.project_manager_user_id = project.project_manager_employee_id.user_id
