from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    project_director_partner_id = fields.Many2one(
        related='company_id.project_director_partner_id',
        readonly=False
    )

    ceo_partner_id = fields.Many2one(
        related='company_id.ceo_partner_id',
        readonly=False
    )
