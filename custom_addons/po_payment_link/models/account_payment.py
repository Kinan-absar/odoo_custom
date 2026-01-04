from odoo import models, fields

class AccountMove(models.Model):
    _inherit = "account.move"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
    )
class AccountPayment(models.Model):
    _inherit = "account.payment"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('purchase','done'))]",
    )

    def action_post(self):
        res = super().action_post()
        for payment in self:
            if payment.purchase_id and payment.move_id:
                payment.move_id.purchase_id = payment.purchase_id
        return res