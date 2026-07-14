from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountReceiptVoucher(models.Model):
    _check_company_auto = True
    _name = 'account.receipt.voucher'
    _description = 'Receipt Voucher'
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
        string='Received From',
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

    # The journal/account that RECEIVES the money (cash box or bank account)
    journal_id = fields.Many2one(
        'account.journal',
        string='Deposit To',
        check_company=True,
        domain="[('default_account_id', '!=', False), ('company_id', '=', company_id)]",
        required=True
    )

    # The account being credited — income, AR, advance received, etc.
    account_id = fields.Many2one(
        'account.account',
        string='Income / Receivable Account',
        check_company=True,
        domain="[('company_ids', 'in', company_id)]",
        required=True
    )

    move_id = fields.Many2one(
        'account.move',
        readonly=True,
        copy=False
    )


    # -------------------------
    # Customer Invoice Matching / Reconciliation
    # -------------------------

    invoice_ids = fields.Many2many(
        'account.move',
        'account_receipt_voucher_invoice_rel',
        'voucher_id',
        'move_id',
        string='Customer Invoices to Reconcile',
        domain="[('partner_id', '=', partner_id), ('company_id', '=', company_id), ('move_type', '=', 'out_invoice'), ('state', '=', 'posted'), ('payment_state', 'in', ('not_paid', 'partial'))]",
        copy=False,
        tracking=True,
    )

    reconciled_invoice_ids = fields.Many2many(
        'account.move',
        'account_receipt_voucher_reconciled_invoice_rel',
        'voucher_id',
        'move_id',
        string='Reconciled Customer Invoices',
        compute='_compute_reconciled_invoice_ids',
        copy=False,
        readonly=True,
    )

    invoice_reconciled = fields.Boolean(
        string='Invoices Reconciled',
        compute='_compute_invoice_reconciled',
        store=True,
    )

    invoice_total = fields.Monetary(
        string='Selected Invoices Residual',
        compute='_compute_invoice_reconciliation_amounts',
        currency_field='currency_id',
    )

    allocated_amount = fields.Monetary(
        string='Allocated Amount',
        compute='_compute_invoice_reconciliation_amounts',
        currency_field='currency_id',
    )

    remaining_to_reconcile = fields.Monetary(
        string='Remaining to Allocate',
        compute='_compute_invoice_reconciliation_amounts',
        currency_field='currency_id',
    )

    difference_amount = fields.Monetary(
        string='Difference',
        compute='_compute_invoice_reconciliation_amounts',
        currency_field='currency_id',
    )

    is_receivable_account = fields.Boolean(
        string='Is Receivable Account',
        compute='_compute_is_receivable_account',
    )

    invoice_reconciliation_state = fields.Selection(
        [
            ('not_applicable', 'Not Applicable'),
            ('no_invoices', 'Not Allocated'),
            ('ready', 'Ready to Allocate'),
            ('partial', 'Partially Allocated'),
            ('reconciled', 'Fully Allocated'),
        ],
        string='Receipt Allocation Status',
        compute='_compute_invoice_reconciliation_state',
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

    receipt_method = fields.Selection(
        [
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
            ('bank_transfer', 'Bank Transfer'),
        ],
        string="Receipt Method",
        required=True,
        default='cash'
    )

    # -------------------------
    # Analytic on Income / Receivable Account
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
    # Customer Invoice Reconciliation
    # -------------------------

    @api.depends('account_id')
    def _compute_is_receivable_account(self):
        for rec in self:
            rec.is_receivable_account = rec.account_id.account_type == 'asset_receivable'

    @api.depends(
        'invoice_ids',
        'invoice_ids.amount_residual',
        'amount',
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
    )
    def _compute_invoice_reconciliation_amounts(self):
        for rec in self:
            rec.invoice_total = sum(rec.invoice_ids.mapped('amount_residual'))
            voucher_lines = rec._get_voucher_receivable_lines()
            if voucher_lines:
                original = sum(abs(line.balance) for line in voucher_lines)
                remaining = sum(abs(line.amount_residual) for line in voucher_lines)
            else:
                original = rec.amount or 0.0
                remaining = rec.amount or 0.0
            rec.allocated_amount = max(original - remaining, 0.0)
            rec.remaining_to_reconcile = remaining
            rec.difference_amount = remaining - rec.invoice_total

    @api.depends(
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
        'account_id', 'partner_id', 'company_id',
    )
    def _compute_reconciled_invoice_ids(self):
        for rec in self:
            invoices = self.env['account.move']
            voucher_lines = rec._get_voucher_receivable_lines()
            if voucher_lines:
                partials = self.env['account.partial.reconcile'].search([
                    '|',
                    ('debit_move_id', 'in', voucher_lines.ids),
                    ('credit_move_id', 'in', voucher_lines.ids),
                ])
                opposite_lines = (partials.mapped('debit_move_id') | partials.mapped('credit_move_id')) - voucher_lines
                invoices = opposite_lines.mapped('move_id').filtered(
                    lambda move: move.move_type == 'out_invoice' and move.company_id == rec.company_id
                )
            rec.reconciled_invoice_ids = invoices

    @api.depends(
        'move_id.line_ids.balance',
        'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled',
        'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
        'account_id', 'partner_id', 'company_id',
    )
    def _compute_invoice_reconciled(self):
        for rec in self:
            voucher_lines = rec._get_voucher_receivable_lines()
            rec.invoice_reconciled = bool(voucher_lines) and all(line.reconciled for line in voucher_lines)

    @api.depends(
        'state', 'account_id', 'account_id.account_type', 'invoice_ids',
        'move_id.line_ids.balance', 'move_id.line_ids.amount_residual',
        'move_id.line_ids.reconciled', 'move_id.line_ids.matched_debit_ids',
        'move_id.line_ids.matched_credit_ids',
    )
    def _compute_invoice_reconciliation_state(self):
        for rec in self:
            if rec.account_id.account_type != 'asset_receivable':
                rec.invoice_reconciliation_state = 'not_applicable'
                continue
            voucher_lines = rec._get_voucher_receivable_lines()
            if voucher_lines:
                remaining = sum(abs(line.amount_residual) for line in voucher_lines)
                original = sum(abs(line.balance) for line in voucher_lines)
                used = original - remaining
                if rec.currency_id.is_zero(remaining):
                    rec.invoice_reconciliation_state = 'reconciled'
                elif rec.currency_id.compare_amounts(used, 0.0) > 0:
                    rec.invoice_reconciliation_state = 'partial'
                elif rec.invoice_ids:
                    rec.invoice_reconciliation_state = 'ready'
                else:
                    rec.invoice_reconciliation_state = 'no_invoices'
            elif rec.invoice_ids:
                rec.invoice_reconciliation_state = 'ready'
            else:
                rec.invoice_reconciliation_state = 'no_invoices'

    def _get_voucher_receivable_lines(self):
        self.ensure_one()
        if not self.move_id or not self.account_id:
            return self.env['account.move.line']
        return self.move_id.line_ids.filtered(
            lambda line: line.account_id == self.account_id
            and line.account_id.account_type == 'asset_receivable'
            and line.partner_id == self.partner_id
            and line.company_id == self.company_id
        )

    def _get_selected_invoice_receivable_lines(self):
        self.ensure_one()
        if not self.invoice_ids or not self.account_id:
            return self.env['account.move.line']
        return self.invoice_ids.line_ids.filtered(
            lambda line: line.account_id == self.account_id
            and line.account_id.account_type == 'asset_receivable'
            and line.partner_id == self.partner_id
            and line.company_id == self.company_id
            and not line.reconciled
        )

    def action_find_matching_invoices(self):
        for rec in self:
            if rec.invoice_reconciled:
                raise UserError(_('This receipt voucher is fully reconciled.'))
            if rec.account_id.account_type != 'asset_receivable':
                raise UserError(_('Invoice matching is available only when the voucher account is Accounts Receivable.'))
            if not rec.partner_id:
                raise UserError(_('Please set the customer first.'))
            invoices = self.env['account.move'].search([
                ('partner_id', '=', rec.partner_id.id),
                ('company_id', '=', rec.company_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
                ('amount_residual', '>', 0),
            ], order='invoice_date asc, date asc, id asc')
            selected = self.env['account.move']
            remaining = rec.remaining_to_reconcile or rec.amount or 0.0
            exact = invoices.filtered(lambda inv: rec.currency_id.compare_amounts(inv.amount_residual, remaining) == 0)
            if exact:
                selected = exact[:1]
            else:
                for inv in invoices:
                    if rec.currency_id.compare_amounts(remaining, 0.0) <= 0:
                        break
                    selected |= inv
                    remaining -= inv.amount_residual
            rec.invoice_ids = [(6, 0, selected.ids)]
            rec.message_post(body=(_('Suggested customer invoice(s): %s') % ', '.join(selected.mapped('name'))) if selected else _('No open customer invoices were found.'))
        return True

    def action_reconcile_invoices(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only posted receipt vouchers can be reconciled.'))
            if rec.account_id.account_type != 'asset_receivable':
                raise UserError(_('The voucher account must be an Accounts Receivable account.'))
            if rec.invoice_reconciled:
                raise UserError(_('This receipt voucher is fully reconciled.'))
            if not rec.invoice_ids:
                raise UserError(_('Please select at least one customer invoice.'))
            voucher_lines = rec._get_voucher_receivable_lines().filtered(lambda line: not line.reconciled)
            invoice_lines = rec._get_selected_invoice_receivable_lines()
            if not voucher_lines:
                raise UserError(_('No unreconciled receivable line was found on the voucher journal entry.'))
            if not invoice_lines:
                raise UserError(_('No unreconciled receivable lines were found on the selected invoices.'))
            all_lines = voucher_lines | invoice_lines
            if len(all_lines.mapped('account_id')) != 1:
                raise UserError(_('All lines must use the same receivable account.'))
            if len(all_lines.mapped('partner_id')) != 1:
                raise UserError(_('All lines must use the same customer.'))
            if len(all_lines.mapped('company_id')) != 1:
                raise UserError(_('All lines must belong to the same company.'))
            invoices = rec.invoice_ids
            all_lines.reconcile()
            rec.with_context(skip_invoice_reconcile_lock=True).write({'invoice_ids': [(5, 0, 0)]})
            rec.message_post(body=_('Reconciled with customer invoice(s): %s') % ', '.join(invoices.mapped('name')))
        return True

    def action_unreconcile_invoices(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only posted receipt vouchers can be unreconciled.'))
            voucher_lines = rec._get_voucher_receivable_lines()
            if not voucher_lines:
                raise UserError(_('No receivable line was found on this voucher.'))
            partials = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', 'in', voucher_lines.ids),
                ('credit_move_id', 'in', voucher_lines.ids),
            ])
            if not partials:
                raise UserError(_('No reconciled invoice lines were found for this voucher.'))
            opposite = (partials.mapped('debit_move_id') | partials.mapped('credit_move_id')) - voucher_lines
            affected = opposite.mapped('move_id').filtered(lambda move: move.move_type == 'out_invoice')
            amount = sum(partials.mapped('amount'))
            partials.unlink()
            rec.with_context(skip_invoice_reconcile_lock=True).write({'invoice_ids': [(5, 0, 0)]})
            rec.message_post(body=_('Unreconciled %.2f from customer invoice(s): %s') % (amount, ', '.join(affected.mapped('name'))))
        return True

    # -------------------------
    # Actions
    # -------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if rec.journal_id.company_id and rec.journal_id.company_id != rec.company_id:
                raise UserError(_("The selected journal belongs to a different company."))

            if rec.account_id.company_ids and rec.company_id not in rec.account_id.company_ids:
                raise UserError(_("The selected account is not available for this company."))

            if not rec.journal_id.default_account_id:
                raise UserError(_("The selected journal has no default account."))

            analytic_vals = {}
            if rec.analytic_distribution:
                analytic_vals['analytic_distribution'] = rec.analytic_distribution

            lines = [
                # Debit: cash/bank journal (money coming in)
                (0, 0, {
                    'account_id': rec.journal_id.default_account_id.id,
                    'partner_id': rec.partner_id.id,
                    'debit': rec.amount,
                    'name': rec.description or rec.name,
                }),
                # Credit: income / receivable account
                (0, 0, {
                    'account_id': rec.account_id.id,
                    'partner_id': rec.partner_id.id,
                    'credit': rec.amount,
                    'name': rec.description or rec.name,
                    **analytic_vals,
                }),
            ]

            if rec.move_id and rec.move_id.state not in ('draft', False):
                raise UserError(_(
                    "This voucher is already linked to journal entry %s which is not in draft state. "
                    "Please reset it to draft before posting again, to avoid creating a duplicate entry."
                ) % rec.move_id.name)

            if rec.move_id and rec.move_id.state == 'draft':
                move = rec.move_id
                move.write({
                    'date': rec.date,
                    'journal_id': rec.journal_id.id,
                    'ref': rec.name,
                    'line_ids': [(5, 0, 0)] + lines,
                })
            else:
                move = self.env['account.move'].with_company(rec.company_id).create({
                    'date': rec.date,
                    'journal_id': rec.journal_id.id,
                    'company_id': rec.company_id.id,
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

            voucher_lines = rec._get_voucher_receivable_lines()
            has_reconciliation = bool(voucher_lines.filtered(
                lambda line: line.reconciled or line.matched_debit_ids or line.matched_credit_ids
                or abs(line.amount_residual) < abs(line.balance)
            ))
            if has_reconciliation:
                raise UserError(_('This voucher has reconciled receivable lines. Unreconcile the customer invoices first.'))

            if rec.move_id and rec.move_id.state == 'posted':
                # Do not use button_draft() for voucher-generated moves because it
                # can delete/rebuild dynamic tax lines and trigger Odoo's tax report
                # protection. Keep the existing move linked and reuse it on repost.
                rec.move_id.sudo().write({'state': 'draft'})

            rec.state = 'draft'

    # -------------------------
    # Deletion Protection
    # -------------------------

    def unlink(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("You cannot delete a posted receipt voucher."))
        return super().unlink()

    # -------------------------
    # Sequence
    # -------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                    'receipt.voucher'
                ) or 'New'
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if rec.state == 'posted':
                allowed_fields = {'state', 'move_id', 'invoice_ids'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(_("You cannot modify a posted receipt voucher."))
                if 'invoice_ids' in vals and rec.invoice_reconciled and not self.env.context.get('skip_invoice_reconcile_lock'):
                    raise UserError(_('You cannot change selected invoices after this voucher has been fully reconciled.'))
        return super().write(vals)


    @api.onchange('company_id')
    def _onchange_company_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id if rec.company_id else self.env.company.currency_id
            rec.journal_id = False
            rec.account_id = False
        return {
            'domain': {
                'journal_id': [('default_account_id', '!=', False), ('company_id', '=', self.company_id.id)] if self.company_id else [('default_account_id', '!=', False)],
                'account_id': [('company_ids', 'in', self.company_id.id)] if self.company_id else [],
            }
        }

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
            'cash_count': count([('receipt_method', '=', 'cash')]),
            'cheque_count': count([('receipt_method', '=', 'cheque')]),
            'bank_count': count([('receipt_method', '=', 'bank_transfer')]),
            'my_count': count([('create_uid', '=', self.env.uid)]),
            'total_posted_amount': total_posted_amount,
            'currency_symbol': self.env.company.currency_id.symbol or '',
        }
