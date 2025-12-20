from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    project_director_partner_id = fields.Many2one(
        'res.partner',
        string="Project Director (Signer)"
    )

    ceo_partner_id = fields.Many2one(
        'res.partner',
        string="CEO (Signer)"
    )
