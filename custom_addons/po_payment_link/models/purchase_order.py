from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    paid_amount = fields.Monetary(
        string="Paid Amount",
        compute="_compute_payment_status",
    )
    remaining_amount = fields.Monetary(
        string="Remaining Amount",
        compute="_compute_payment_status",
    )
    payment_status = fields.Selection(
        [
            ("not_paid", "Not Paid"),
            ("partial", "Partially Paid"),
            ("paid", "Paid"),
        ],
        string="Payment Status",
        compute="_compute_payment_status",
    )

    @api.depends("amount_total")
    def _compute_payment_status(self):
        for po in self:
            paid = 0.0

            payments = self.env["account.payment"].search([
                ("state", "=", "posted"),
                ("purchase_id", "=", po.id),
                ("company_id", "=", po.company_id.id),
            ])

            for payment in payments:
                for line in payment.move_id.line_ids:
                    if line.account_id.account_type == "liability_payable":
                        paid += abs(line.balance)

            po.paid_amount = paid
            po.remaining_amount = po.amount_total - paid

            if paid <= 0:
                po.payment_status = "not_paid"
            elif paid < po.amount_total:
                po.payment_status = "partial"
            else:
                po.payment_status = "paid"
