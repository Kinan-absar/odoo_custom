from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPaymentVoucher(models.Model):
    _check_company_auto = True
    _name = 'account.payment.voucher'
    _description = 'Payment Voucher'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # -------------------------
    # Basic Info
    # -------------------------

    name = fields.Char(
        default='New',
        readonly=True,
        copy=False
    )

    date = fields.Date(
        default=fields.Date.context_today,
        required=True
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True
    )

    amount = fields.Monetary(
        required=True,
        tracking=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        check_company=True,
        domain="[('default_account_id', '!=', False)]",
        required=True
    )

    # Used for pay-to-account mode (vendor, expense, advance)
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        check_company=True,
        domain="[]",
    )

    # Used for journal-to-journal transfer mode
    line_ids = fields.One2many(
        'account.payment.voucher.line',
        'voucher_id',
        string='Destination Journals'
    )

    move_id = fields.Many2one(
        'account.move',
        readonly=True,
        copy=False
    )


    # -------------------------
    # Vendor Bill Matching / Reconciliation
    # -------------------------

    bill_ids = fields.Many2many(
        'account.move',
        'account_payment_voucher_bill_rel',
        'voucher_id',
        'move_id',
        string='Vendor Bills to Reconcile',
        domain="[('partner_id', '=', partner_id), ('company_id', '=', company_id), ('move_type', '=', 'in_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]",
        copy=False,
        tracking=True,
    )

    # -------------------------
    # Purchase Order Tracking
    # -------------------------

    # Kept for backward compatibility with vouchers created by earlier versions.
    # New vouchers should use po_allocation_ids so one payment can be split safely
    # between several purchase orders without counting the full amount on each PO.
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Legacy Purchase Order',
        check_company=True,
        domain="[('partner_id', '=', partner_id), ('company_id', '=', company_id), ('state', 'in', ('purchase', 'done'))]",
        tracking=True,
        copy=False,
        help="Legacy single-PO link retained so existing vouchers remain intact.",
    )

    po_allocation_ids = fields.One2many(
        'account.payment.voucher.po.allocation',
        'voucher_id',
        string='Purchase Order Allocations',
        copy=True,
    )

    purchase_order_ids = fields.Many2many(
        'purchase.order',
        'account_payment_voucher_purchase_order_rel_v2',
        'voucher_id',
        'purchase_order_id',
        string='Purchase Orders',
        domain="[('partner_id', '=', partner_id), ('company_id', '=', company_id), ('state', 'in', ('purchase', 'done'))]",
        tracking=True,
        copy=False,
        help='Select one or more Purchase Orders covered by this payment.',
    )

    po_allocated_amount = fields.Monetary(
        string='Allocated to Purchase Orders',
        compute='_compute_po_allocation_totals',
        store=True,
        currency_field='currency_id',
    )

    po_unallocated_amount = fields.Monetary(
        string='Unallocated PO Amount',
        compute='_compute_po_allocation_totals',
        store=True,
        currency_field='currency_id',
    )

    reconciled_bill_ids = fields.Many2many(
        'account.move',
        'account_payment_voucher_reconciled_bill_rel',
        'voucher_id',
        'move_id',
        string='Reconciled Vendor Bills',
        compute='_compute_reconciled_bill_ids',
        copy=False,
        readonly=True,
    )

    bill_reconciled = fields.Boolean(
        string='Bills Reconciled',
        compute='_compute_bill_reconciled',
        store=True,
    )

    bill_total = fields.Monetary(
        string='Selected Bills Residual',
        compute='_compute_bill_reconciliation_amounts',
        currency_field='currency_id',
    )

    difference_amount = fields.Monetary(
        string='Difference',
        compute='_compute_bill_reconciliation_amounts',
        currency_field='currency_id',
    )

    allocated_amount = fields.Monetary(
        string='Allocated Amount',
        compute='_compute_bill_reconciliation_amounts',
        currency_field='currency_id',
    )

    remaining_to_reconcile = fields.Monetary(
        string='Remaining to Allocate',
        compute='_compute_bill_reconciliation_amounts',
        currency_field='currency_id',
    )

    is_payable_account = fields.Boolean(
        string='Is Payable Account',
        compute='_compute_is_payable_account',
    )

    bill_reconciliation_state = fields.Selection(
        [
            ('not_applicable', 'Not Applicable'),
            ('no_bills', 'Not Allocated'),
            ('ready', 'Ready to Allocate'),
            ('partial', 'Partially Allocated'),
            ('reconciled', 'Fully Allocated'),
        ],
        string='Payment Allocation Status',
        compute='_compute_bill_reconciliation_state',
        store=True,
    )

    reconciliation_list_status = fields.Selection(
        [
            ('not_reconciled', 'Not Fully Allocated'),
            ('reconciled', 'Fully Allocated'),
        ],
        string='Legacy Allocation List Status',
        compute='_compute_reconciliation_list_status',
        store=True,
    )


    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('cancel', 'Cancelled')
        ],
        default='draft',
        tracking=True
    )

    description = fields.Text(string="Notes")

    payment_method = fields.Selection(
        [
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('bank_transfer', 'Bank Transfer'),
            ('journal_transfer', 'Journal Transfer'),
        ],
        string="Payment Method",
        required=True,
        default='cash'
    )

    # -------------------------
    # Bank Fees
    # -------------------------

    has_bank_fees = fields.Boolean(string="Bank Fees")

    fee_amount = fields.Monetary(string="Bank Fee Amount")

    fee_account_id = fields.Many2one(
        'account.account',
        string="Bank Fee Account",
        domain="[]"
    )

    fee_tax_id = fields.Many2one(
        'account.tax',
        string="VAT on Bank Fee",
        domain="[('type_tax_use','=','purchase')]"
    )

    fee_analytic_distribution = fields.Json(
        string="Fee Analytic Distribution"
    )

    fee_analytic_precision = fields.Integer(
        default=2,
        readonly=True
    )

    # -------------------------
    # Analytic on Account
    # -------------------------

    analytic_distribution = fields.Json(
        string="Analytic Distribution"
    )

    analytic_precision = fields.Integer(
        default=2,
        readonly=True
    )

    # -------------------------
    # Amount in Words
    # -------------------------

    amount_in_words_ar = fields.Char(
        string="Amount in Words (Arabic)",
        compute="_compute_amount_in_words_ar"
    )

    def _compute_amount_in_words_ar(self):
        ar_installed = bool(
            self.env['res.lang'].search([('code', '=', 'ar_001')], limit=1)
        )
        for rec in self:
            amount_for_words = rec.amount

            if rec.payment_method == 'journal_transfer':
                amount_for_words = sum(rec.line_ids.mapped('amount'))

            if amount_for_words and rec.currency_id:
                if ar_installed:
                    rec.amount_in_words_ar = rec.currency_id.with_context(
                        lang='ar_001'
                    ).amount_to_text(amount_for_words)
                else:
                    rec.amount_in_words_ar = rec.currency_id.amount_to_text(amount_for_words)
            else:
                rec.amount_in_words_ar = ''


    @api.depends('account_id')
    def _compute_is_payable_account(self):
        for rec in self:
            rec.is_payable_account = rec.account_id.account_type == 'liability_payable'

    @api.depends(
        'bill_ids',
        'bill_ids.amount_residual',
        'amount',
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
    )
    def _compute_bill_reconciliation_amounts(self):
        for rec in self:
            rec.bill_total = sum(rec.bill_ids.mapped('amount_residual'))

            voucher_lines = rec._get_voucher_payable_lines()
            if voucher_lines:
                original = sum(abs(line.balance) for line in voucher_lines)
                remaining = sum(abs(line.amount_residual) for line in voucher_lines)
            else:
                original = rec.amount or 0.0
                remaining = rec.amount or 0.0

            rec.allocated_amount = max(original - remaining, 0.0)
            rec.remaining_to_reconcile = remaining
            rec.difference_amount = remaining - rec.bill_total

    @api.depends(
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
        'account_id',
        'partner_id',
        'company_id',
    )
    def _compute_reconciled_bill_ids(self):
        for rec in self:
            bills = self.env['account.move']
            voucher_lines = rec._get_voucher_payable_lines()
            if voucher_lines:
                partials = self.env['account.partial.reconcile'].search([
                    '|',
                    ('debit_move_id', 'in', voucher_lines.ids),
                    ('credit_move_id', 'in', voucher_lines.ids),
                ])
                opposite_lines = (partials.mapped('debit_move_id') | partials.mapped('credit_move_id')) - voucher_lines
                bills = opposite_lines.mapped('move_id').filtered(
                    lambda move: move.move_type == 'in_invoice' and move.company_id == rec.company_id
                )
            rec.reconciled_bill_ids = bills

    @api.depends(
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
        'account_id',
        'partner_id',
        'company_id',
    )
    def _compute_bill_reconciled(self):
        for rec in self:
            voucher_lines = rec._get_voucher_payable_lines()
            rec.bill_reconciled = bool(voucher_lines) and all(line.reconciled for line in voucher_lines)

    @api.depends(
        'state',
        'account_id',
        'account_id.account_type',
        'payment_method',
        'bill_ids',
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
    )
    def _compute_bill_reconciliation_state(self):
        for rec in self:
            if rec.payment_method == 'journal_transfer' or rec.account_id.account_type != 'liability_payable':
                rec.bill_reconciliation_state = 'not_applicable'
                continue

            voucher_lines = rec._get_voucher_payable_lines()
            if voucher_lines:
                remaining = sum(abs(line.amount_residual) for line in voucher_lines)
                original = sum(abs(line.balance) for line in voucher_lines)
                used = original - remaining

                if rec.currency_id.is_zero(remaining):
                    rec.bill_reconciliation_state = 'reconciled'
                elif rec.currency_id.compare_amounts(used, 0.0) > 0:
                    rec.bill_reconciliation_state = 'partial'
                elif rec.bill_ids:
                    rec.bill_reconciliation_state = 'ready'
                else:
                    rec.bill_reconciliation_state = 'no_bills'
                continue

            if rec.bill_ids:
                rec.bill_reconciliation_state = 'ready'
            else:
                rec.bill_reconciliation_state = 'no_bills'

    @api.depends('bill_reconciliation_state')
    def _compute_reconciliation_list_status(self):
        for rec in self:
            rec.reconciliation_list_status = 'reconciled' if rec.bill_reconciliation_state == 'reconciled' else 'not_reconciled'

    def _get_voucher_payable_lines(self):
        self.ensure_one()
        if not self.move_id or not self.account_id:
            return self.env['account.move.line']
        return self.move_id.line_ids.filtered(
            lambda line: line.account_id == self.account_id
            and line.account_id.account_type == 'liability_payable'
            and line.partner_id == self.partner_id
            and line.company_id == self.company_id
        )

    def _get_selected_bill_payable_lines(self):
        self.ensure_one()
        if not self.bill_ids or not self.account_id:
            return self.env['account.move.line']
        return self.bill_ids.line_ids.filtered(
            lambda line: line.account_id == self.account_id
            and line.account_id.account_type == 'liability_payable'
            and line.partner_id == self.partner_id
            and line.company_id == self.company_id
            and not line.reconciled
        )

    def action_find_matching_bills(self):
        """Find open vendor bills for the same vendor/account/company.

        This action only suggests bills. The user can still edit the selected
        bills before clicking Reconcile Bills.
        """
        for rec in self:
            if rec.bill_reconciled:
                raise UserError(_("This payment voucher is fully reconciled. You cannot find or replace bills after full reconciliation."))
            if rec.payment_method == 'journal_transfer':
                raise UserError(_("Bill matching is only available for Cash, Cheque, and Bank Transfer payment vouchers."))
            if rec.account_id.account_type != 'liability_payable':
                raise UserError(_("Bill matching is only available when the voucher account is Accounts Payable."))
            if not rec.partner_id:
                raise UserError(_("Please set the vendor/partner first."))

            bills = self.env['account.move'].search([
                ('partner_id', '=', rec.partner_id.id),
                ('company_id', '=', rec.company_id.id),
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
                ('amount_residual', '>', 0),
            ], order='invoice_date asc, date asc, id asc')

            selected_bills = self.env['account.move']
            remaining = rec.remaining_to_reconcile or rec.amount or 0.0

            exact_bills = bills.filtered(lambda bill: rec.currency_id.compare_amounts(bill.amount_residual, remaining) == 0)
            if exact_bills:
                selected_bills = exact_bills[:1]
            else:
                for bill in bills:
                    if rec.currency_id.compare_amounts(remaining, 0.0) <= 0:
                        break
                    selected_bills |= bill
                    remaining -= bill.amount_residual
                    if rec.currency_id.compare_amounts(remaining, 0.0) <= 0:
                        break

            rec.bill_ids = [(6, 0, selected_bills.ids)]
            if selected_bills:
                rec.message_post(body=_("Suggested vendor bill(s): %s") % ', '.join(selected_bills.mapped('name')))
            else:
                rec.message_post(body=_("No open vendor bills were found for this vendor."))
        return True

    def action_reconcile_bills(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_("Only posted payment vouchers can be reconciled."))
            if rec.payment_method == 'journal_transfer':
                raise UserError(_("Vendor bill reconciliation is not available for Journal Transfer vouchers."))
            if rec.account_id.account_type != 'liability_payable':
                raise UserError(_("The voucher account must be an Accounts Payable account."))
            if rec.bill_reconciled:
                raise UserError(_("This payment voucher is fully reconciled."))
            if not rec.bill_ids:
                raise UserError(_("Please select at least one vendor bill to reconcile."))
            if not rec.move_id:
                raise UserError(_("This payment voucher has no posted journal entry."))

            voucher_lines = rec._get_voucher_payable_lines().filtered(lambda line: not line.reconciled)
            bill_lines = rec._get_selected_bill_payable_lines()

            if not voucher_lines:
                raise UserError(_("No unreconciled payable line was found on the voucher journal entry."))
            if not bill_lines:
                raise UserError(_("No unreconciled payable lines were found on the selected vendor bills."))

            all_lines = voucher_lines | bill_lines
            accounts = all_lines.mapped('account_id')
            partners = all_lines.mapped('partner_id')
            companies = all_lines.mapped('company_id')

            if len(accounts) != 1:
                raise UserError(_("All lines must use the same payable account."))
            if len(partners) != 1:
                raise UserError(_("All lines must use the same vendor/partner."))
            if len(companies) != 1:
                raise UserError(_("All lines must belong to the same company."))

            bills_to_reconcile = rec.bill_ids
            all_lines.reconcile()
            rec.with_context(skip_bill_reconcile_lock=True).write({
                'bill_ids': [(5, 0, 0)],
            })
            rec.message_post(body=_("Reconciled with vendor bill(s): %s") % ', '.join(bills_to_reconcile.mapped('name')))
        return True

    def action_unreconcile_bills(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_("Only posted payment vouchers can be unreconciled."))
            if not rec.move_id:
                raise UserError(_("This payment voucher has no posted journal entry."))

            voucher_lines = rec._get_voucher_payable_lines()
            if not voucher_lines:
                raise UserError(_("No payable line was found on this voucher."))

            # IMPORTANT: only remove partial reconciliations directly connected to
            # this voucher's payable line. Do not call remove_move_reconcile() on
            # the invoice lines, because that can remove reconciliations made by
            # other payment vouchers against the same bill.
            partials = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', 'in', voucher_lines.ids),
                ('credit_move_id', 'in', voucher_lines.ids),
            ])
            if not partials:
                raise UserError(_("No reconciled payable lines were found to unreconcile for this voucher."))

            opposite_lines = (partials.mapped('debit_move_id') | partials.mapped('credit_move_id')) - voucher_lines
            affected_bills = opposite_lines.mapped('move_id').filtered(lambda move: move.move_type == 'in_invoice')
            amount = sum(partials.mapped('amount'))

            partials.unlink()
            rec.with_context(skip_bill_reconcile_lock=True).write({
                'bill_ids': [(5, 0, 0)],
            })
            rec.message_post(body=_("Unreconciled %.2f from vendor bill(s): %s") % (amount, ', '.join(affected_bills.mapped('name'))))
        return True

    # -------------------------
    # Constraints
    # -------------------------

    @api.constrains('payment_method', 'account_id', 'line_ids')
    def _check_payment_mode(self):
        for rec in self:
            if rec.payment_method == 'journal_transfer':
                if not rec.line_ids:
                    raise UserError(_("Please add at least one destination journal."))
            else:
                if not rec.account_id:
                    raise UserError(_("Please set an account."))

    @api.constrains('line_ids', 'amount', 'has_bank_fees', 'fee_amount', 'fee_tax_id')
    def _check_destination_total(self):
        for rec in self:
            if rec.payment_method != 'journal_transfer' or not rec.line_ids:
                continue

            destination_total = sum(rec.line_ids.mapped('amount'))
            expected_amount = rec.amount

            if rec.has_bank_fees and rec.fee_amount:
                tax_amount = 0.0
                if rec.fee_tax_id:
                    tax_amount = sum(
                        t['amount']
                        for t in rec.fee_tax_id.compute_all(
                            rec.fee_amount,
                            currency=rec.currency_id
                        )['taxes']
                    )
                expected_amount -= (rec.fee_amount + tax_amount)

            if not rec.currency_id.is_zero(destination_total - expected_amount):
                raise UserError(_(
                    "Destination total (%.2f) must equal net transfer amount (%.2f)."
                ) % (destination_total, expected_amount))

    @api.constrains('has_bank_fees', 'fee_amount', 'fee_account_id', 'payment_method')
    def _check_bank_fees(self):
        for rec in self:
            if rec.has_bank_fees:
                if rec.payment_method not in ('bank_transfer', 'journal_transfer'):
                    raise UserError(_(
                        "Bank fees are only applicable for Bank Transfer or Journal Transfer."
                    ))
                if not rec.fee_account_id:
                    raise UserError(_("Please set a bank fee account."))
                if rec.fee_amount <= 0:
                    raise UserError(_("Bank fee amount must be greater than zero."))

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.payment_method in ('cash', 'cheque'):
            self.has_bank_fees = False
            self.fee_amount = 0.0
            self.fee_account_id = False
            self.fee_tax_id = False
            self.fee_analytic_distribution = False
            self.line_ids = [(5, 0, 0)]
        if self.payment_method != 'journal_transfer':
            self.line_ids = [(5, 0, 0)]

    def _sync_po_allocations_from_selector(self):
        """Synchronize allocation records only for persisted vouchers and POs.

        Do not build required One2many rows during a browser onchange. Odoo uses
        temporary NewId records there, which can result in an allocation row with
        an empty purchase_order_id. This method runs only after create/write, when
        both the voucher and selected purchase orders have real database IDs.
        """
        if self.env.context.get('skip_po_allocation_sync'):
            return

        Allocation = self.env['account.payment.voucher.po.allocation']
        for voucher in self.filtered(lambda v: bool(v.id)):
            selected_orders = voucher.purchase_order_ids.exists()
            existing = voucher.po_allocation_ids

            # Remove allocations for POs no longer selected.
            to_remove = existing.filtered(
                lambda line: line.purchase_order_id not in selected_orders
            )
            if to_remove:
                to_remove.with_context(
                    skip_po_selector_sync=True,
                    skip_po_allocation_sync=True,
                ).unlink()

            # Create missing rows only with real PO IDs.
            existing_order_ids = set(
                voucher.po_allocation_ids.mapped('purchase_order_id').ids
            )
            vals_list = [
                {
                    'voucher_id': voucher.id,
                    'purchase_order_id': order.id,
                    'amount': 0.0,
                }
                for order in selected_orders
                if order.id and order.id not in existing_order_ids
            ]
            if vals_list:
                Allocation.with_context(
                    skip_po_selector_sync=True,
                    skip_po_allocation_sync=True,
                ).create(vals_list)

    @api.depends('po_allocation_ids.amount', 'amount')
    def _compute_po_allocation_totals(self):
        for rec in self:
            allocated = sum(rec.po_allocation_ids.mapped('amount'))
            rec.po_allocated_amount = allocated
            rec.po_unallocated_amount = rec.amount - allocated

    @api.constrains('po_allocation_ids', 'po_allocation_ids.amount',
                    'po_allocation_ids.purchase_order_id', 'amount',
                    'partner_id', 'company_id')
    def _check_po_allocations(self):
        for rec in self:
            if not rec.po_allocation_ids:
                continue

            orders = rec.po_allocation_ids.mapped('purchase_order_id')
            if len(orders) != len(rec.po_allocation_ids):
                raise ValidationError(_("The same Purchase Order cannot be allocated twice on one voucher."))

            wrong_partner = orders.filtered(lambda po: po.partner_id.commercial_partner_id != rec.partner_id.commercial_partner_id)
            if wrong_partner:
                raise ValidationError(_("All selected Purchase Orders must belong to the voucher vendor."))

            wrong_company = orders.filtered(lambda po: po.company_id != rec.company_id)
            if wrong_company:
                raise ValidationError(_("All selected Purchase Orders must belong to the voucher company."))

            allocated = sum(rec.po_allocation_ids.mapped('amount'))
            if rec.currency_id.compare_amounts(allocated, rec.amount) > 0:
                raise ValidationError(_(
                    "The total Purchase Order allocation (%(allocated)s) cannot exceed the voucher amount (%(amount)s).",
                    allocated=allocated,
                    amount=rec.amount,
                ))

    @api.onchange('purchase_order_id')
    def _onchange_purchase_order_id(self):
        """When a Purchase Order is picked, default the partner and suggest
        any open vendor bills generated from that order so the user can
        reconcile the payment straight away."""
        if self.purchase_order_id:
            if not self.partner_id:
                self.partner_id = self.purchase_order_id.partner_id

            if self.payment_method != 'journal_transfer':
                bills = self.env['account.move'].search([
                    ('invoice_line_ids.purchase_line_id.order_id', '=', self.purchase_order_id.id),
                    ('move_type', '=', 'in_invoice'),
                    ('state', '=', 'posted'),
                    ('payment_state', 'in', ('not_paid', 'partial')),
                ])
                if bills:
                    self.bill_ids = [(6, 0, bills.ids)]


    def _write_line_amounts_safely(self, line, debit=0.0, credit=0.0, account=None, partner=None, name=None, analytic_distribution=None, tax_ids=None):
        """Update an existing draft move line without deleting protected tax lines."""
        vals = {
            'debit': debit or 0.0,
            'credit': credit or 0.0,
        }
        if account:
            vals['account_id'] = account.id
        if partner:
            vals['partner_id'] = partner.id
        if name is not None:
            vals['name'] = name
        if analytic_distribution is not None:
            vals['analytic_distribution'] = analytic_distribution or False
        if tax_ids is not None:
            vals['tax_ids'] = [(6, 0, tax_ids.ids)] if tax_ids else [(5, 0, 0)]
        line.with_context(check_move_validity=False).write(vals)

    def _update_existing_move_lines_without_deleting_tax(self, move, debit_line_data, credit_line_data, fee_line_data=None, tax_amount=0.0):
        """Update voucher-generated draft move lines when tax lines already exist.

        Odoo may block deleting tax lines after they affected the tax report. Therefore,
        on repost we update the existing base, bank, fee, and generated tax lines in-place
        instead of using (5, 0, 0) to remove all lines.
        """
        self.ensure_one()
        rec = self
        lines = move.line_ids
        tax_lines = lines.filtered(lambda line: line.tax_line_id or (line.tax_repartition_line_id and not line.tax_ids))

        fee_lines = lines.filtered(lambda line: line.tax_ids or (rec.fee_account_id and line.account_id == rec.fee_account_id and not line.tax_line_id))
        fee_line = fee_lines[:1]

        bank_lines = lines.filtered(lambda line: line.account_id == rec.journal_id.default_account_id and not line.tax_line_id and line not in fee_lines)
        bank_line = bank_lines.filtered(lambda line: line.credit > 0)[:1] or bank_lines[:1]

        base_lines = lines.filtered(lambda line: line not in tax_lines and line not in fee_lines and line not in bank_lines)
        debit_line = base_lines.filtered(lambda line: line.account_id == rec.account_id)[:1] or base_lines[:1]

        if not debit_line:
            debit_line = self.env['account.move.line'].with_context(check_move_validity=False).create({
                'move_id': move.id,
                'account_id': debit_line_data['account'].id,
                'partner_id': rec.partner_id.id,
                'debit': debit_line_data['debit'],
                'credit': debit_line_data['credit'],
                'name': debit_line_data['name'],
                'analytic_distribution': debit_line_data.get('analytic_distribution') or False,
            })
        else:
            rec._write_line_amounts_safely(
                debit_line,
                debit=debit_line_data['debit'],
                credit=debit_line_data['credit'],
                account=debit_line_data['account'],
                partner=rec.partner_id,
                name=debit_line_data['name'],
                analytic_distribution=debit_line_data.get('analytic_distribution') or False,
                tax_ids=False,
            )

        if fee_line_data:
            if not fee_line:
                fee_line = self.env['account.move.line'].with_context(check_move_validity=False).create({
                    'move_id': move.id,
                    'account_id': fee_line_data['account'].id,
                    'partner_id': rec.partner_id.id,
                    'debit': fee_line_data['debit'],
                    'credit': fee_line_data['credit'],
                    'name': fee_line_data['name'],
                    'tax_ids': [(6, 0, fee_line_data['tax_ids'].ids)] if fee_line_data.get('tax_ids') else [],
                    'analytic_distribution': fee_line_data.get('analytic_distribution') or False,
                })
            else:
                rec._write_line_amounts_safely(
                    fee_line,
                    debit=fee_line_data['debit'],
                    credit=fee_line_data['credit'],
                    account=fee_line_data['account'],
                    partner=rec.partner_id,
                    name=fee_line_data['name'],
                    analytic_distribution=fee_line_data.get('analytic_distribution') or False,
                    tax_ids=fee_line_data.get('tax_ids'),
                )
        else:
            # Keep protected old fee/tax lines but neutralize their value.
            if fee_line:
                rec._write_line_amounts_safely(fee_line, debit=0.0, credit=0.0, tax_ids=False)
            tax_amount = 0.0

        if tax_lines:
            for tax_line in tax_lines:
                rec._write_line_amounts_safely(tax_line, debit=0.0, credit=0.0)
            main_tax_line = tax_lines[:1]
            if tax_amount:
                rec._write_line_amounts_safely(main_tax_line, debit=tax_amount, credit=0.0)

        if not bank_line:
            self.env['account.move.line'].with_context(check_move_validity=False).create({
                'move_id': move.id,
                'account_id': credit_line_data['account'].id,
                'partner_id': rec.partner_id.id,
                'debit': credit_line_data['debit'],
                'credit': credit_line_data['credit'],
                'name': credit_line_data['name'],
            })
        else:
            rec._write_line_amounts_safely(
                bank_line,
                debit=credit_line_data['debit'],
                credit=credit_line_data['credit'],
                account=credit_line_data['account'],
                partner=rec.partner_id,
                name=credit_line_data['name'],
                tax_ids=False,
            )

        # Neutralize any extra old non-tax lines so previous data does not remain active.
        active_lines = debit_line | fee_line | bank_line | tax_lines
        extra_lines = lines - active_lines
        for extra in extra_lines:
            rec._write_line_amounts_safely(extra, debit=0.0, credit=0.0, tax_ids=False)

        # Final safety: make the bank line exactly balance the final draft move.
        # This prevents Odoo from adding an "Automatic Balancing Line" on repost.
        # Do this after fee/tax lines are updated because Odoo may recompute tax amounts
        # with rounding. We never delete protected tax lines here.
        move.invalidate_recordset(['line_ids'])
        auto_lines = move.line_ids.filtered(
            lambda line: (line.name or '') == 'Automatic Balancing Line'
        )
        protected_tax_lines = move.line_ids.filtered(
            lambda line: line.tax_line_id or line.tax_repartition_line_id
        )
        balancing_base_lines = move.line_ids - bank_line - auto_lines
        target_bank_balance = -sum(balancing_base_lines.mapped('balance'))
        if target_bank_balance >= 0:
            rec._write_line_amounts_safely(
                bank_line,
                debit=target_bank_balance,
                credit=0.0,
                account=credit_line_data['account'],
                partner=rec.partner_id,
                name=credit_line_data['name'],
                tax_ids=False,
            )
        else:
            rec._write_line_amounts_safely(
                bank_line,
                debit=0.0,
                credit=abs(target_bank_balance),
                account=credit_line_data['account'],
                partner=rec.partner_id,
                name=credit_line_data['name'],
                tax_ids=False,
            )

        # Remove only useless zero automatic balancing lines. These are not tax lines,
        # and deleting them does not touch the tax report. If any automatic line has a
        # value, stop instead of hiding an imbalance.
        move.invalidate_recordset(['line_ids'])
        auto_lines = move.line_ids.filtered(
            lambda line: (line.name or '') == 'Automatic Balancing Line'
        )
        non_zero_auto_lines = auto_lines.filtered(
            lambda line: not move.currency_id.is_zero(line.debit) or not move.currency_id.is_zero(line.credit)
        )
        if non_zero_auto_lines:
            raise UserError(_(
                "The journal entry is still not balanced and Odoo created an Automatic Balancing Line. "
                "Please check the voucher amount, bank fees, and tax setup."
            ))
        zero_auto_lines = auto_lines - protected_tax_lines
        if zero_auto_lines:
            zero_auto_lines.with_context(check_move_validity=False).unlink()

    # -------------------------
    # Actions
    # -------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.journal_id.default_account_id:
                raise UserError(_("The selected journal has no default account."))

            if rec.po_allocation_ids and any(line.amount <= 0 for line in rec.po_allocation_ids):
                raise UserError(_("Enter an allocated amount greater than zero for every selected Purchase Order."))

            if rec.payment_method == 'journal_transfer':
                rec._post_journal_transfer()
            else:
                rec._post_account_payment()

    def _post_account_payment(self):
        """Cash / Cheque / Bank Transfer — pay against an account."""
        rec = self
        if not rec.account_id:
            raise UserError(_("Please set an account."))

        if rec.has_bank_fees and not rec.fee_account_id:
            raise UserError(_("Please set a bank fee account."))

        lines = []

        expense_analytic = {}
        if rec.analytic_distribution:
            expense_analytic['analytic_distribution'] = rec.analytic_distribution

        fee_analytic = {}
        if rec.fee_analytic_distribution:
            fee_analytic['analytic_distribution'] = rec.fee_analytic_distribution

        # 1. Debit: account (expense / advance / payable)
        lines.append((0, 0, {
            'account_id': rec.account_id.id,
            'partner_id': rec.partner_id.id,
            'debit': rec.amount,
            'name': rec.description or rec.name,
            **expense_analytic,
        }))

        if rec.has_bank_fees and rec.fee_amount:
            # 2. Debit: fee account
            lines.append((0, 0, {
                'account_id': rec.fee_account_id.id,
                'partner_id': rec.partner_id.id,
                'debit': rec.fee_amount,
                'tax_ids': [(6, 0, rec.fee_tax_id.ids)] if rec.fee_tax_id else [],
                'name': _('Bank Fees'),
                **fee_analytic,
            }))

            tax_amount = 0.0
            if rec.fee_tax_id:
                tax_amount = sum(
                    t['amount']
                    for t in rec.fee_tax_id.compute_all(
                        rec.fee_amount, currency=rec.currency_id
                    )['taxes']
                )

            # 3. Credit: journal (amount + fees + tax)
            lines.append((0, 0, {
                'account_id': rec.journal_id.default_account_id.id,
                'partner_id': rec.partner_id.id,
                'credit': rec.amount + rec.fee_amount + tax_amount,
                'name': rec.description or rec.name,
            }))
        else:
            # 3. Credit: journal (no fees)
            lines.append((0, 0, {
                'account_id': rec.journal_id.default_account_id.id,
                'partner_id': rec.partner_id.id,
                'credit': rec.amount,
                'name': rec.description or rec.name,
            }))

        if rec.move_id and rec.move_id.state not in ('draft', False):
            raise UserError(_(
                "This voucher is already linked to journal entry %s which is not in draft state. "
                "Please reset it to draft before posting again, to avoid creating a duplicate entry."
            ) % rec.move_id.name)

        if rec.move_id and rec.move_id.state == 'draft':
            move = rec.move_id
            move_vals = {
                'date': rec.date,
                'journal_id': rec.journal_id.id,
                'ref': rec.name,
            }
            has_tax_lines = bool(move.line_ids.filtered(
                lambda line: line.tax_line_id or line.tax_ids or line.tax_repartition_line_id
            ))
            if has_tax_lines:
                debit_data = {
                    'account': rec.account_id,
                    'debit': rec.amount,
                    'credit': 0.0,
                    'name': rec.description or rec.name,
                    'analytic_distribution': rec.analytic_distribution,
                }
                fee_data = False
                tax_amount = 0.0
                if rec.has_bank_fees and rec.fee_amount:
                    if rec.fee_tax_id:
                        tax_amount = sum(t['amount'] for t in rec.fee_tax_id.compute_all(rec.fee_amount, currency=rec.currency_id)['taxes'])
                    fee_data = {
                        'account': rec.fee_account_id,
                        'debit': rec.fee_amount,
                        'credit': 0.0,
                        'name': _('Bank Fees'),
                        'analytic_distribution': rec.fee_analytic_distribution,
                        'tax_ids': rec.fee_tax_id,
                    }
                credit_data = {
                    'account': rec.journal_id.default_account_id,
                    'debit': 0.0,
                    'credit': rec.amount + (rec.fee_amount if fee_data else 0.0) + tax_amount,
                    'name': rec.description or rec.name,
                }
                move.with_context(check_move_validity=False).write(move_vals)
                rec._update_existing_move_lines_without_deleting_tax(move, debit_data, credit_data, fee_data, tax_amount)
            else:
                move_vals['line_ids'] = [(5, 0, 0)] + lines
                move.write(move_vals)
        else:
            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.journal_id.id,
                'ref': rec.name,
                'line_ids': lines,
            })
            rec.move_id = move.id
        move.action_post()
        rec.state = 'posted'

    def _post_journal_transfer(self):
        """Journal Transfer — move funds between journals."""
        rec = self
        if not rec.line_ids:
            raise UserError(_("Please add at least one destination journal."))

        if rec.has_bank_fees and not rec.fee_account_id:
            raise UserError(_("Please set a bank fee account."))

        lines = []
        net_amount = rec.amount

        fee_analytic = {}
        if rec.fee_analytic_distribution:
            fee_analytic['analytic_distribution'] = rec.fee_analytic_distribution

        # 1. Credit: source journal
        lines.append((0, 0, {
            'account_id': rec.journal_id.default_account_id.id,
            'credit': rec.amount,
            'name': rec.description or rec.name,
        }))

        # 2. Bank fees
        if rec.has_bank_fees and rec.fee_amount:
            lines.append((0, 0, {
                'account_id': rec.fee_account_id.id,
                'debit': rec.fee_amount,
                'tax_ids': [(6, 0, rec.fee_tax_id.ids)] if rec.fee_tax_id else [],
                'name': _('Bank Fees'),
                **fee_analytic,
            }))

            tax_amount = 0.0
            if rec.fee_tax_id:
                tax_amount = sum(
                    t['amount']
                    for t in rec.fee_tax_id.compute_all(
                        rec.fee_amount, currency=rec.currency_id
                    )['taxes']
                )
            net_amount -= (rec.fee_amount + tax_amount)

        if net_amount <= 0:
            raise UserError(_("Net transferred amount must be greater than zero after fees."))

        # 3. Debit: each destination journal
        for line in rec.line_ids:
            if not line.journal_id.default_account_id:
                raise UserError(_(
                    "Destination journal '%s' has no default account."
                ) % line.journal_id.name)
            lines.append((0, 0, {
                'account_id': line.journal_id.default_account_id.id,
                'debit': line.amount,
                'name': rec.description or rec.name,
            }))

        if rec.move_id and rec.move_id.state not in ('draft', False):
            raise UserError(_(
                "This voucher is already linked to journal entry %s which is not in draft state. "
                "Please reset it to draft before posting again, to avoid creating a duplicate entry."
            ) % rec.move_id.name)

        if rec.move_id and rec.move_id.state == 'draft':
            move = rec.move_id
            move_vals = {
                'date': rec.date,
                'journal_id': rec.journal_id.id,
                'ref': rec.name,
            }
            has_tax_lines = bool(move.line_ids.filtered(
                lambda line: line.tax_line_id or line.tax_ids or line.tax_repartition_line_id
            ))
            if has_tax_lines:
                raise UserError(_(
                    "This journal transfer contains protected VAT lines. To change amounts or fees after posting, "
                    "create a new transfer or reverse the old one instead of deleting tax lines."
                ))
            else:
                move_vals['line_ids'] = [(5, 0, 0)] + lines
                move.write(move_vals)
        else:
            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.journal_id.id,
                'ref': rec.name,
                'line_ids': lines,
            })
            rec.move_id = move.id
        move.action_post()
        rec.state = 'posted'

    def action_cancel(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("Reset to draft before cancelling."))
            rec.state = 'cancel'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ('posted', 'cancel'):
                continue

            # Safety net: do not allow resetting the voucher journal entry
            # while any payable line has full or partial reconciliation attached.
            voucher_lines = rec._get_voucher_payable_lines()
            has_reconciled_payable_lines = bool(voucher_lines.filtered(
                lambda line: line.reconciled
                or line.matched_debit_ids
                or line.matched_credit_ids
                or abs(line.amount_residual) < abs(line.balance)
            ))
            if has_reconciled_payable_lines:
                raise UserError(_(
                    "This voucher has reconciled payable lines. Unreconcile the vendor bills first before resetting it to draft."
                ))

            if rec.move_id and rec.move_id.state == 'posted':
                # Important: do NOT call button_draft() here. These journal entries
                # are generated by this custom voucher module and may contain dynamic
                # VAT lines for bank fees. In Odoo 17/18, button_draft() can try to
                # delete/rebuild those tax lines and raises:
                # "You cannot delete a tax line as it would impact the tax report".
                # We only need to reuse the same linked move on repost, so safely put
                # the same move back to draft without touching its lines.
                rec.move_id.sudo().write({'state': 'draft'})

            rec.state = 'draft'

    # -------------------------
    # Deletion Protection
    # -------------------------

    def unlink(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("You cannot delete a posted payment voucher."))
        return super().unlink()

    # -------------------------
    # Sequence
    # -------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'payment.voucher'
                ) or 'New'
        records = super().create(vals_list)
        records._sync_po_allocations_from_selector()
        return records

    def write(self, vals):
        for rec in self:
            if rec.state == 'posted':
                allowed_fields = {'state', 'move_id', 'bill_ids'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(_("You cannot modify a posted payment voucher."))
                if 'bill_ids' in vals and rec.bill_reconciled and not self.env.context.get('skip_bill_reconcile_lock'):
                    raise UserError(_("You cannot change selected bills after this voucher has been fully reconciled."))
        result = super().write(vals)
        if 'purchase_order_ids' in vals and not self.env.context.get('skip_po_allocation_sync'):
            self._sync_po_allocations_from_selector()
        return result

    @api.model
    def retrieve_dashboard(self):
        company_domain = [('company_id', 'in', self.env.companies.ids)]

        def count(domain):
            return self.search_count(company_domain + domain)

        total_posted = self.read_group(
            company_domain + [('state', '=', 'posted')],
            ['amount:sum'],
            []
        )

        total_posted_amount = total_posted[0].get('amount', 0.0) if total_posted else 0.0

        return {
            'all_count': count([]),
            'draft_count': count([('state', '=', 'draft')]),
            'posted_count': count([('state', '=', 'posted')]),
            'cancel_count': count([('state', '=', 'cancel')]),

            'cash_count': count([('payment_method', '=', 'cash')]),
            'cheque_count': count([('payment_method', '=', 'cheque')]),
            'bank_count': count([('payment_method', '=', 'bank_transfer')]),
            'transfer_count': count([('payment_method', '=', 'journal_transfer')]),

            'my_count': count([('create_uid', '=', self.env.uid)]),
            'fully_allocated_count': count([('bill_reconciliation_state', '=', 'reconciled')]),
            'not_allocated_count': count([('bill_reconciliation_state', '=', 'no_bills')]),
            'partial_allocated_count': count([('bill_reconciliation_state', '=', 'partial')]),
            'ready_to_allocate_count': count([('bill_reconciliation_state', '=', 'ready')]),
            'total_posted_amount': total_posted_amount,
            'currency_symbol': self.env.company.currency_id.symbol or '',
        }


class AccountPaymentVoucherPOAllocation(models.Model):
    _name = 'account.payment.voucher.po.allocation'
    _description = 'Payment Voucher Purchase Order Allocation'
    # Use a dedicated fresh table. A previous failed development upgrade may
    # have left the default table partially created without voucher_id.
    _table = 'account_payment_voucher_po_allocation_v2'
    _order = 'id'
    _check_company_auto = True

    voucher_id = fields.Many2one(
        'account.payment.voucher',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=False,
        ondelete='restrict',
        index=True,
        check_company=True,
    )
    amount = fields.Monetary(
        string='Allocated Amount',
        required=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='voucher_id.currency_id',
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related='voucher_id.company_id',
        store=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='voucher_id.partner_id',
        store=True,
        readonly=True,
    )
    voucher_state = fields.Selection(
        related='voucher_id.state',
        string='Status',
        store=True,
        readonly=True,
    )
    po_currency_id = fields.Many2one(
        related='purchase_order_id.currency_id',
        readonly=True,
    )
    po_total = fields.Monetary(
        related='purchase_order_id.amount_total',
        string='PO Total',
        currency_field='po_currency_id',
        readonly=True,
    )
    po_balance_due = fields.Monetary(
        related='purchase_order_id.amount_paid_residual',
        string='PO Balance Due',
        currency_field='po_currency_id',
        readonly=True,
    )

    def init(self):
        """Remove incomplete rows left by earlier failed development upgrades."""
        self.env.cr.execute("""
            DELETE FROM account_payment_voucher_po_allocation_v2
             WHERE voucher_id IS NULL OR purchase_order_id IS NULL
        """)

    _sql_constraints = [
        ('voucher_po_unique', 'unique(voucher_id, purchase_order_id)',
         'The same Purchase Order cannot be allocated twice on one voucher.'),
        ('allocation_amount_nonnegative', 'check(amount >= 0)',
         'The allocated amount cannot be negative.'),
    ]

    @api.constrains('purchase_order_id', 'voucher_id')
    def _check_order_matches_voucher(self):
        for line in self:
            if not line.purchase_order_id or not line.voucher_id:
                continue
            if line.purchase_order_id.company_id != line.voucher_id.company_id:
                raise ValidationError(_("The Purchase Order and payment voucher must belong to the same company."))
            if line.purchase_order_id.partner_id.commercial_partner_id != line.voucher_id.partner_id.commercial_partner_id:
                raise ValidationError(_("The Purchase Order must belong to the same vendor as the payment voucher."))

    def _sync_voucher_purchase_orders(self, vouchers):
        if self.env.context.get('skip_po_selector_sync'):
            return
        for voucher in vouchers:
            orders = voucher.po_allocation_ids.mapped('purchase_order_id')
            if voucher.purchase_order_id:
                orders |= voucher.purchase_order_id
            voucher.with_context(skip_po_selector_sync=True).write({
                'purchase_order_ids': [(6, 0, orders.ids)],
            })

    @api.model_create_multi
    def create(self, vals_list):
        vouchers = self.env['account.payment.voucher'].browse(
            [vals.get('voucher_id') for vals in vals_list if vals.get('voucher_id')]
        )
        if any(v.state != 'draft' for v in vouchers):
            raise UserError(_("Purchase Order allocations can only be changed while the voucher is in Draft."))
        records = super().create(vals_list)
        records._sync_voucher_purchase_orders(records.mapped('voucher_id'))
        return records

    def write(self, vals):
        vouchers = self.mapped('voucher_id')
        if any(v.state != 'draft' for v in vouchers):
            raise UserError(_("Purchase Order allocations can only be changed while the voucher is in Draft."))
        result = super().write(vals)
        self._sync_voucher_purchase_orders(vouchers | self.mapped('voucher_id'))
        return result

    def unlink(self):
        vouchers = self.mapped('voucher_id')
        if any(v.state != 'draft' for v in vouchers):
            raise UserError(_("Purchase Order allocations can only be changed while the voucher is in Draft."))
        result = super().unlink()
        self._sync_voucher_purchase_orders(vouchers)
        return result
class AccountPaymentVoucherLine(models.Model):
    _name = 'account.payment.voucher.line'
    _description = 'Payment Voucher Destination Journal'

    voucher_id = fields.Many2one(
        'account.payment.voucher',
        required=True,
        ondelete='cascade'
    )

    journal_id = fields.Many2one(
        'account.journal',
        string='Destination Journal',
        required=True,
        domain="[('default_account_id','!=',False)]"
    )

    amount = fields.Monetary(required=True)

    currency_id = fields.Many2one(
        related='voucher_id.currency_id',
        store=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            voucher_id = vals.get('voucher_id')
            if voucher_id:
                voucher = self.env['account.payment.voucher'].browse(voucher_id)
                if voucher.state == 'posted':
                    raise UserError(
                        _("You cannot add lines to a posted voucher.")
                    )
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            if line.voucher_id.state == 'posted':
                raise UserError(_("You cannot modify lines of a posted voucher."))
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.voucher_id.state == 'posted':
                raise UserError(_("You cannot delete lines of a posted voucher."))
        return super().unlink()
