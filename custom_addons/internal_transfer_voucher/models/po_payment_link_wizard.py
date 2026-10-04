from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class PurchaseOrderLinkPaymentVoucherWizard(models.TransientModel):
    _name = 'purchase.order.link.payment.voucher.wizard'
    _description = 'Link Existing Payment to Purchase Order'

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
    commercial_partner_id = fields.Many2one(
        'res.partner',
        string='Commercial Vendor',
        related='purchase_order_id.partner_id.commercial_partner_id',
        readonly=True,
    )
    payment_source = fields.Selection(
        [
            ('voucher', 'Payment Voucher'),
            ('odoo', 'Odoo Vendor Payment'),
        ],
        string='Payment Type',
        required=True,
        default='voucher',
    )
    voucher_id = fields.Many2one(
        'account.payment.voucher',
        string='Payment Voucher',
        domain="[('partner_id.commercial_partner_id', '=', commercial_partner_id), ('company_id', '=', company_id), ('state', '=', 'posted')]",
        help='Posted Payment Vouchers for the same vendor and company.',
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Vendor Payment',
        domain="[('partner_id.commercial_partner_id', '=', commercial_partner_id), ('company_id', '=', company_id), ('payment_type', '=', 'outbound'), ('partner_type', '=', 'supplier'), ('move_id.state', '=', 'posted')]",
        help='Posted standard Odoo vendor payments for the same vendor and company.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_selected_payment_values',
        readonly=True,
    )
    payment_amount = fields.Monetary(
        string='Payment Amount',
        compute='_compute_selected_payment_values',
        currency_field='currency_id',
        readonly=True,
    )
    already_allocated = fields.Monetary(
        string='Already Allocated',
        compute='_compute_selected_payment_values',
        currency_field='currency_id',
        readonly=True,
    )
    available_to_allocate = fields.Monetary(
        string='Available to Allocate',
        compute='_compute_selected_payment_values',
        currency_field='currency_id',
        readonly=True,
    )
    amount = fields.Monetary(
        string='Amount to Allocate',
        required=True,
        currency_field='currency_id',
    )

    @api.depends(
        'payment_source',
        'voucher_id', 'voucher_id.amount', 'voucher_id.po_allocation_ids.amount',
        'payment_id', 'payment_id.amount', 'payment_id.purchase_order_allocation_ids.amount',
    )
    def _compute_selected_payment_values(self):
        for wizard in self:
            currency = wizard.company_id.currency_id
            payment_amount = 0.0
            allocated = 0.0

            if wizard.payment_source == 'voucher' and wizard.voucher_id:
                currency = wizard.voucher_id.currency_id
                payment_amount = wizard.voucher_id.amount
                allocated = sum(wizard.voucher_id.po_allocation_ids.mapped('amount'))
            elif wizard.payment_source == 'odoo' and wizard.payment_id:
                currency = wizard.payment_id.currency_id
                payment_amount = wizard.payment_id.amount
                allocated = sum(wizard.payment_id.purchase_order_allocation_ids.mapped('amount'))

            wizard.currency_id = currency
            wizard.payment_amount = payment_amount
            wizard.already_allocated = allocated
            wizard.available_to_allocate = max(payment_amount - allocated, 0.0)

    @api.onchange('payment_source')
    def _onchange_payment_source(self):
        for wizard in self:
            wizard.voucher_id = False
            wizard.payment_id = False
            wizard.amount = 0.0

    @api.onchange('voucher_id', 'payment_id')
    def _onchange_selected_payment(self):
        for wizard in self:
            wizard.amount = wizard.available_to_allocate

    def action_link_payment(self):
        self.ensure_one()
        order = self.purchase_order_id

        if self.amount <= 0:
            raise ValidationError(_('The allocation amount must be greater than zero.'))

        if self.payment_source == 'voucher':
            voucher = self.voucher_id
            if not voucher or voucher.state != 'posted':
                raise UserError(_('Please select a posted Payment Voucher.'))
            if voucher.company_id != order.company_id:
                raise ValidationError(_('The Payment Voucher and Purchase Order must belong to the same company.'))
            if voucher.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id:
                raise ValidationError(_('The Payment Voucher must belong to the same vendor as the Purchase Order.'))
            if voucher.po_allocation_ids.filtered(lambda line: line.purchase_order_id == order):
                raise ValidationError(_('This Payment Voucher is already linked to this Purchase Order.'))
            currency = voucher.currency_id
        else:
            payment = self.payment_id
            if not payment or not payment.move_id or payment.move_id.state != 'posted':
                raise UserError(_('Please select a posted Odoo vendor payment.'))
            if payment.payment_type != 'outbound' or payment.partner_type != 'supplier':
                raise ValidationError(_('Only outbound vendor payments can be linked to a Purchase Order.'))
            if payment.company_id != order.company_id:
                raise ValidationError(_('The vendor payment and Purchase Order must belong to the same company.'))
            if payment.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id:
                raise ValidationError(_('The vendor payment must belong to the same vendor as the Purchase Order.'))
            if payment.purchase_order_allocation_ids.filtered(lambda line: line.purchase_order_id == order):
                raise ValidationError(_('This vendor payment is already linked to this Purchase Order.'))
            currency = payment.currency_id

        precision = currency.decimal_places
        if float_compare(self.amount, self.available_to_allocate, precision_digits=precision) > 0:
            raise ValidationError(_(
                'The allocation amount cannot exceed the unallocated payment amount of %(amount).2f %(currency)s.',
                amount=self.available_to_allocate,
                currency=currency.name,
            ))

        if self.payment_source == 'voucher':
            voucher._link_posted_purchase_order(order, self.amount)
            source_name = voucher.display_name
            source_label = _('Payment Voucher')
            source_record = voucher
        else:
            allocation = self.env['account.payment.po.allocation'].create({
                'payment_id': self.payment_id.id,
                'purchase_order_id': order.id,
                'amount': self.amount,
            })
            source_name = self.payment_id.display_name
            source_label = _('Odoo Vendor Payment')
            source_record = self.payment_id
            # Make the stored PO totals recompute immediately after the allocation is created.
            order.invalidate_recordset(['standard_payment_allocation_ids', 'amount_paid', 'amount_paid_residual'])

        message = _(
            '%(source_label)s %(source)s was linked to Purchase Order %(po)s with an allocation of %(amount).2f %(currency)s. '
            'The posted accounting entry was not changed.',
            source_label=source_label,
            source=source_name,
            po=order.display_name,
            amount=self.amount,
            currency=currency.name,
        )
        if hasattr(source_record, 'message_post'):
            source_record.message_post(body=message)
        if hasattr(order, 'message_post'):
            order.message_post(body=message)

        return {'type': 'ir.actions.act_window_close'}

    # Backward compatibility for any old XML/button reference.
    def action_link_voucher(self):
        return self.action_link_payment()
