from odoo import models, fields

class AccountPayment(models.Model):
    _inherit = "account.payment"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('purchase','done'))]",
    )
