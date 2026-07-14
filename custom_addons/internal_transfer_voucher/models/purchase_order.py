from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_voucher_allocation_ids = fields.One2many(
        'account.payment.voucher.po.allocation',
        'purchase_order_id',
        string='Payment Voucher Allocations',
    )

    # Compatibility field for old vouchers that used one single PO link.
    legacy_payment_voucher_ids = fields.One2many(
        'account.payment.voucher',
        'purchase_order_id',
        string='Legacy Payment Vouchers',
    )

    payment_voucher_ids = fields.Many2many(
        'account.payment.voucher',
        string='Payment Vouchers',
        compute='_compute_payment_totals',
        readonly=True,
    )

    amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_payment_totals',
        currency_field='currency_id',
        store=True,
        help='Total amount allocated from posted payment vouchers to this Purchase Order.',
    )

    amount_paid_residual = fields.Monetary(
        string='Balance Due',
        compute='_compute_payment_totals',
        currency_field='currency_id',
        store=True,
    )

    payment_voucher_count = fields.Integer(
        string='Payment Voucher Count',
        compute='_compute_payment_totals',
        store=True,
    )

    @api.depends(
        'payment_voucher_allocation_ids.amount',
        'payment_voucher_allocation_ids.voucher_id.state',
        'payment_voucher_allocation_ids.voucher_id.date',
        'payment_voucher_allocation_ids.voucher_id.currency_id',
        'legacy_payment_voucher_ids.amount',
        'legacy_payment_voucher_ids.state',
        'legacy_payment_voucher_ids.date',
        'legacy_payment_voucher_ids.currency_id',
        'legacy_payment_voucher_ids.po_allocation_ids',
        'amount_total',
        'currency_id',
        'company_id',
    )
    def _compute_payment_totals(self):
        for order in self:
            allocations = order.payment_voucher_allocation_ids.filtered(
                lambda line: line.voucher_id.state == 'posted'
            )
            vouchers = allocations.mapped('voucher_id')
            paid = 0.0

            for line in allocations:
                voucher = line.voucher_id
                paid += voucher.currency_id._convert(
                    line.amount,
                    order.currency_id,
                    order.company_id,
                    voucher.date or fields.Date.context_today(order),
                )

            # Old vouchers remain counted only when they have no new allocation lines.
            legacy = order.legacy_payment_voucher_ids.filtered(
                lambda voucher: voucher.state == 'posted' and not voucher.po_allocation_ids
            )
            vouchers |= legacy
            for voucher in legacy:
                paid += voucher.currency_id._convert(
                    voucher.amount,
                    order.currency_id,
                    order.company_id,
                    voucher.date or fields.Date.context_today(order),
                )

            order.payment_voucher_ids = vouchers
            order.amount_paid = paid
            order.amount_paid_residual = order.amount_total - paid
            order.payment_voucher_count = len(vouchers)

    def action_view_payment_vouchers(self):
        self.ensure_one()
        return {
            'name': 'Payment Vouchers',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.voucher',
            'view_mode': 'list,form',
            'domain': ['|', ('po_allocation_ids.purchase_order_id', '=', self.id),
                       ('purchase_order_id', '=', self.id)],
            'context': {'default_partner_id': self.partner_id.id},
        }
