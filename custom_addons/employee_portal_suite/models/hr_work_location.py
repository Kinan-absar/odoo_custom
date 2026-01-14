from odoo import models, fields

class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=False,  # TEMPORARY
        ondelete="restrict",
        help="Project linked to this work location. Used for approvals and routing."
    )
