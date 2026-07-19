from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class PurchaseOrderLinkPaymentVoucherWizard(models.TransientModel):
    _name = 'purchase.order.link.payment.voucher.wizard'
    _description = 'Link Existing Payment Voucher to Purchase Order'

    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='purchase_order_id.partner_id',
        readonly=True,
    )
    company_id = fields.Many2one(
        related='purchase_order_id.company_id',
        readonly=True,
    )
    voucher_id = fields.Many2one(
        'account.payment.voucher',
        string='Payment Voucher',
        required=True,
        domain="[('partner_id.commercial_partner_id', '=', partner_id.commercial_partner_id), ('company_id', '=', company_id), ('state', '=', 'posted')]",
        help='Only posted payment vouchers for the same vendor and company are available.',
    )
    voucher_currency_id = fields.Many2one(
        related='voucher_id.currency_id',
        readonly=True,
    )
    voucher_amount = fields.Monetary(
        related='voucher_id.amount',
        currency_field='voucher_currency_id',
        readonly=True,
    )
    already_allocated = fields.Monetary(
        string='Already Allocated',
        compute='_compute_voucher_amounts',
        currency_field='voucher_currency_id',
        readonly=True,
    )
    available_to_allocate = fields.Monetary(
        string='Available to Allocate',
        compute='_compute_voucher_amounts',
        currency_field='voucher_currency_id',
        readonly=True,
    )
    amount = fields.Monetary(
        string='Amount to Allocate',
        required=True,
        currency_field='voucher_currency_id',
    )

    @api.depends('voucher_id', 'voucher_id.amount', 'voucher_id.po_allocation_ids.amount')
    def _compute_voucher_amounts(self):
        for wizard in self:
            allocated = sum(wizard.voucher_id.po_allocation_ids.mapped('amount')) if wizard.voucher_id else 0.0
            wizard.already_allocated = allocated
            wizard.available_to_allocate = max((wizard.voucher_id.amount if wizard.voucher_id else 0.0) - allocated, 0.0)

    @api.onchange('voucher_id')
    def _onchange_voucher_id(self):
        for wizard in self:
            wizard.amount = wizard.available_to_allocate if wizard.voucher_id else 0.0

    def action_link_voucher(self):
        self.ensure_one()
        order = self.purchase_order_id
        voucher = self.voucher_id

        if not voucher or voucher.state != 'posted':
            raise UserError(_('Please select a posted payment voucher.'))
        if voucher.company_id != order.company_id:
            raise ValidationError(_('The payment voucher and Purchase Order must belong to the same company.'))
        if voucher.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id:
            raise ValidationError(_('The payment voucher must belong to the same vendor as the Purchase Order.'))
        if voucher.po_allocation_ids.filtered(lambda line: line.purchase_order_id == order):
            raise ValidationError(_('This payment voucher is already linked to this Purchase Order.'))
        if self.amount <= 0:
            raise ValidationError(_('The allocation amount must be greater than zero.'))

        precision = voucher.currency_id.decimal_places
        if float_compare(self.amount, self.available_to_allocate, precision_digits=precision) > 0:
            raise ValidationError(_(
                'The allocation amount cannot exceed the unallocated voucher amount of %(amount).2f %(currency)s.',
                amount=self.available_to_allocate,
                currency=voucher.currency_id.name,
            ))

        # Update the selector and allocation through one controlled backend path.
        # The posted journal entry is not changed; this is a PO reporting allocation only.
        voucher._link_posted_purchase_order(order, self.amount)

        message = _(
            'Payment voucher %(voucher)s was linked to Purchase Order %(po)s with an allocation of %(amount).2f %(currency)s. '
            'The posted journal entry was not changed.',
            voucher=voucher.display_name,
            po=order.display_name,
            amount=self.amount,
            currency=voucher.currency_id.name,
        )
        if hasattr(voucher, 'message_post'):
            voucher.message_post(body=message)
        if hasattr(order, 'message_post'):
            order.message_post(body=message)

        return {'type': 'ir.actions.act_window_close'}
