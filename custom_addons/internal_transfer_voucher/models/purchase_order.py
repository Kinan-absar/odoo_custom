from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_voucher_ids = fields.One2many(
        'account.payment.voucher',
        'purchase_order_id',
        string='Payment Vouchers',
    )

    amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_amount_paid',
        currency_field='currency_id',
        store=True,
        help="Total of all Posted payment vouchers linked to this Purchase Order.",
    )

    amount_paid_residual = fields.Monetary(
        string='Balance Due',
        compute='_compute_amount_paid',
        currency_field='currency_id',
        store=True,
        help="Purchase Order total minus the amount already paid through linked payment vouchers.",
    )

    payment_voucher_count = fields.Integer(
        string='Payment Voucher Count',
        compute='_compute_amount_paid',
        store=True,
    )

    @api.depends('payment_voucher_ids.amount', 'payment_voucher_ids.state', 'amount_total')
    def _compute_amount_paid(self):
        for order in self:
            posted_vouchers = order.payment_voucher_ids.filtered(lambda v: v.state == 'posted')
            paid = sum(posted_vouchers.mapped('amount'))
            order.amount_paid = paid
            order.amount_paid_residual = order.amount_total - paid
            order.payment_voucher_count = len(posted_vouchers)

    def action_view_payment_vouchers(self):
        self.ensure_one()
        action = {
            'name': 'Payment Vouchers',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.voucher',
            'view_mode': 'list,form',
            'domain': [('purchase_order_id', '=', self.id)],
            'context': {'default_purchase_order_id': self.id, 'default_partner_id': self.partner_id.id},
        }
        return action
