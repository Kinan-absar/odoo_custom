from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    paid_amount = fields.Monetary(
        compute="_compute_payment_status",
        store=True,
    )

    remaining_amount = fields.Monetary(
        compute="_compute_payment_status",
        store=True,
    )

    payment_status = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
        ],
        compute="_compute_payment_status",
        store=True,
    )


    @api.depends("amount_total")
    def _compute_payment_status(self):
        for po in self:
            paid = 0.0

            move_lines = self.env["account.move.line"].search([
                ("move_id.state", "=", "posted"),
                ("account_id.account_type", "=", "liability_payable"),
                ("move_id.purchase_id", "=", po.id),
                ("company_id", "=", po.company_id.id),
            ])

            for line in move_lines:
                paid += abs(line.balance)

            po.paid_amount = paid
            po.remaining_amount = po.amount_total - paid

            if paid <= 0:
                po.payment_status = "not_paid"
            elif paid < po.amount_total:
                po.payment_status = "partial"
            else:
                po.payment_status = "paid"
