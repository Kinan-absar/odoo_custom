from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Upgrade compatibility only. No current configuration screen uses these.
    project_director_partner_id = fields.Many2one(
        related="company_id.project_director_partner_id",
        readonly=False,
    )
    ceo_partner_id = fields.Many2one(
        related="company_id.ceo_partner_id",
        readonly=False,
    )
