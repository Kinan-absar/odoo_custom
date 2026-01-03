from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('purchase','done'))]",
        help="Optional. Select the Purchase Order this payment relates to."
    )
