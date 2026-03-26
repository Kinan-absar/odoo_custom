from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountPaymentVoucher(models.Model):
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
        domain="[('default_account_id', '!=', False)]",
        required=True
    )

    # Used for pay-to-account mode (vendor, expense, advance)
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        domain="[('deprecated','=',False)]",
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
        domain="[('deprecated','=',False)]"
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
            if rec.amount and rec.currency_id:
                if ar_installed:
                    rec.amount_in_words_ar = rec.currency_id.with_context(
                        lang='ar_001'
                    ).amount_to_text(rec.amount)
                else:
                    rec.amount_in_words_ar = rec.currency_id.amount_to_text(rec.amount)
            else:
                rec.amount_in_words_ar = ''

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

    # -------------------------
    # Actions
    # -------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if rec.move_id:
                raise UserError(_("This voucher is already posted."))

            if not rec.journal_id.default_account_id:
                raise UserError(_("The selected journal has no default account."))

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

        move = self.env['account.move'].create({
            'date': rec.date,
            'journal_id': rec.journal_id.id,
            'ref': rec.name,
            'line_ids': lines,
        })
        move.action_post()
        rec.move_id = move.id
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

        move = self.env['account.move'].create({
            'date': rec.date,
            'journal_id': rec.journal_id.id,
            'ref': rec.name,
            'line_ids': lines,
        })
        move.action_post()
        rec.move_id = move.id
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
            if rec.move_id:
                rec.move_id.button_draft()
                rec.move_id.unlink()
            rec.move_id = False
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

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'payment.voucher'
            ) or 'New'
        return super().create(vals)

    def write(self, vals):
        for rec in self:
            if rec.state == 'posted':
                allowed_fields = {'state', 'move_id'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(_("You cannot modify a posted payment voucher."))
        return super().write(vals)


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
