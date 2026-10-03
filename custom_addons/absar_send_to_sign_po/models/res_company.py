from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Legacy compatibility fields.
    # They are intentionally kept so databases upgrading from older releases
    # can load the previous Company > PO Signers inherited view before the
    # cleanup XML deactivates it. The configurable signing engine does NOT use
    # these fields anymore.
    project_director_partner_id = fields.Many2one(
        "res.partner",
        string="Project Director (Signer) [Legacy]",
        help="Legacy compatibility field. Configure signers under Document Signing > Signing Workflows instead.",
    )
    ceo_partner_id = fields.Many2one(
        "res.partner",
        string="CEO (Signer) [Legacy]",
        help="Legacy compatibility field. Configure signers under Document Signing > Signing Workflows instead.",
    )
