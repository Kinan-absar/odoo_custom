from odoo import models, fields

class AccountMove(models.Model):
    _inherit = "account.move"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
    )
