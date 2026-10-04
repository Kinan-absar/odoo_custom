from odoo import models, fields, api, _


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    purchase_order_allocation_ids = fields.One2many(
        'account.payment.po.allocation',
        'payment_id',
        string='Purchase Order Allocations',
        copy=False,
    )


class AccountPaymentPOAllocation(models.Model):
    _name = 'account.payment.po.allocation'
    _description = 'Odoo Vendor Payment Purchase Order Allocation'
    _order = 'id'
    _check_company_auto = True

    payment_id = fields.Many2one(
        'account.payment',
        string='Vendor Payment',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    amount = fields.Monetary(
        string='Allocated Amount',
        required=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='payment_id.currency_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='payment_id.company_id',
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='payment_id.partner_id',
        store=True,
        readonly=True,
    )
    payment_date = fields.Date(
        related='payment_id.date',
        string='Payment Date',
        store=True,
        readonly=True,
    )
    payment_state = fields.Selection(
        related='payment_id.state',
        string='Status',
        store=True,
        readonly=True,
    )

    _sql_constraints = [
        ('payment_po_unique', 'unique(payment_id, purchase_order_id)',
         'This vendor payment is already linked to this Purchase Order.'),
        ('positive_amount', 'check(amount > 0)', 'The allocated amount must be greater than zero.'),
    ]


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    payment_voucher_allocation_ids = fields.One2many(
        'account.payment.voucher.po.allocation',
        'purchase_order_id',
        string='Payment Voucher Allocations',
    )

    standard_payment_allocation_ids = fields.One2many(
        'account.payment.po.allocation',
        'purchase_order_id',
        string='Odoo Vendor Payment Allocations',
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
        store=True,
        compute_sudo=True,
        readonly=True,
    )

    standard_payment_ids = fields.Many2many(
        'account.payment',
        string='Odoo Vendor Payments',
        compute='_compute_payment_totals',
        store=True,
        compute_sudo=True,
        readonly=True,
    )

    amount_paid = fields.Monetary(
        string='Amount Paid',
        compute='_compute_payment_totals',
        currency_field='currency_id',
        store=True,
        compute_sudo=True,
        help='Total amount allocated from Payment Vouchers and standard Odoo vendor payments to this Purchase Order.',
    )

    amount_paid_residual = fields.Monetary(
        string='Balance Due',
        compute='_compute_payment_totals',
        currency_field='currency_id',
        store=True,
        compute_sudo=True,
    )

    payment_voucher_count = fields.Integer(
        string='Payment Count',
        compute='_compute_payment_totals',
        store=True,
        compute_sudo=True,
    )

    @api.depends(
        'payment_voucher_allocation_ids.amount',
        'payment_voucher_allocation_ids.voucher_id.state',
        'payment_voucher_allocation_ids.voucher_id.date',
        'payment_voucher_allocation_ids.voucher_id.currency_id',
        'standard_payment_allocation_ids.amount',
        'standard_payment_allocation_ids.payment_id.state',
        'standard_payment_allocation_ids.payment_id.move_id.state',
        'standard_payment_allocation_ids.payment_id.date',
        'standard_payment_allocation_ids.payment_id.currency_id',
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

            standard_allocations = order.standard_payment_allocation_ids.filtered(
                lambda line: line.payment_id.move_id and line.payment_id.move_id.state == 'posted'
            )
            standard_payments = standard_allocations.mapped('payment_id')
            for line in standard_allocations:
                payment = line.payment_id
                paid += payment.currency_id._convert(
                    line.amount,
                    order.currency_id,
                    order.company_id,
                    payment.date or fields.Date.context_today(order),
                )

            order.payment_voucher_ids = vouchers
            order.standard_payment_ids = standard_payments
            order.amount_paid = paid
            order.amount_paid_residual = order.amount_total - paid
            order.payment_voucher_count = len(vouchers) + len(standard_payments)

    def action_new_payment_voucher(self):
        self.ensure_one()
        default_amount = max(self.amount_paid_residual, 0.0)
        return {
            'name': 'New Payment Voucher',
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.voucher',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
                'default_purchase_order_ids': [(6, 0, [self.id])],
                'default_po_allocation_ids': [(0, 0, {
                    'purchase_order_id': self.id,
                    'amount': default_amount,
                })],
                'default_amount': default_amount,
            },
        }

    def action_link_existing_payment_voucher(self):
        self.ensure_one()
        return {
            'name': _('Link Existing Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order.link.payment.voucher.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_purchase_order_id': self.id,
            },
        }

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
