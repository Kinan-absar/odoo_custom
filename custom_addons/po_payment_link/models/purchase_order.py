from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    paid_amount = fields.Monetary(
        string="Paid Amount",
        compute="_compute_payment_status",
        store=False,
    )

    remaining_amount = fields.Monetary(
        string="Remaining Amount",
        compute="_compute_payment_status",
        store=False,
    )

    payment_status = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
        ],
        string="Payment Status",
        compute="_compute_payment_status",
        store=False,
    )

    @api.depends("amount_total")
    def _compute_payment_status(self):
        for po in self:
            payments = self.env["account.move"].search([
                ("move_type", "=", "outbound"),   # vendor payments
                ("state", "=", "posted"),
                ("purchase_id", "=", po.id),
            ])

            paid = sum(payments.mapped("amount_total"))

            po.paid_amount = paid
            po.remaining_amount = po.amount_total - paid

            if paid == 0:
                po.payment_status = "not_paid"
            elif paid < po.amount_total:
                po.payment_status = "partial"
            else:
                po.payment_status = "paid"
