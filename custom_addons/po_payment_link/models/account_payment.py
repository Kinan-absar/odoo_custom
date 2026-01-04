from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
    )

    def _post(self, soft=True):
        """
        This is the REAL posting method used by Odoo for payments.
        We must propagate the PO here, not in account.payment.action_post().
        """
        res = super()._post(soft=soft)

        for move in self:
            # Only for vendor payments created from account.payment
            if move.payment_id and move.payment_id.purchase_id:
                move.purchase_id = move.payment_id.purchase_id

        return res


class AccountPayment(models.Model):
    _inherit = "account.payment"

    purchase_id = fields.Many2one(
        "purchase.order",
        string="Related Purchase Order",
        domain="[('partner_id', '=', partner_id), ('state', 'in', ('purchase','done'))]",
    )
