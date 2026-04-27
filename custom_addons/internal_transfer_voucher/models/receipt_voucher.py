from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountReceiptVoucher(models.Model):
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
        domain="[('default_account_id', '!=', False)]",
        required=True
    )

    # The account being credited — income, AR, advance received, etc.
    account_id = fields.Many2one(
        'account.account',
        string='Income / Receivable Account',
        domain="[]",
        required=True
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
                raise UserError(_("You cannot delete a posted receipt voucher."))
        return super().unlink()

    # -------------------------
    # Sequence
    # -------------------------

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'receipt.voucher'
            ) or 'New'
        return super().create(vals)

    def write(self, vals):
        for rec in self:
            if rec.state == 'posted':
                allowed_fields = {'state', 'move_id'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(_("You cannot modify a posted receipt voucher."))
        return super().write(vals)

    @api.model
    def retrieve_dashboard(self):
        company_domain = [('company_id', 'in', self.env.companies.ids)]
        my_domain = company_domain + [('create_uid', '=', self.env.uid)]

        def count(domain):
            return self.search_count(company_domain + domain)

        def my_count(domain):
            return self.search_count(my_domain + domain)

        def sum_posted(extra_domain):
            res = self.read_group(
                company_domain + [('state', '=', 'posted')] + extra_domain,
                ['amount:sum'], []
            )
            return res[0].get('amount', 0.0) if res else 0.0

        return {
            # All row
            'draft_count':   count([('state', '=', 'draft')]),
            'posted_count':  count([('state', '=', 'posted')]),
            'cancel_count':  count([('state', '=', 'cancel')]),
            'cash_count':    count([('receipt_method', '=', 'cash')]),
            'cheque_count':  count([('receipt_method', '=', 'cheque')]),
            'bank_count':    count([('receipt_method', '=', 'bank_transfer')]),
            'total_posted_amount': sum_posted([]),

            # My row
            'my_draft_count':   my_count([('state', '=', 'draft')]),
            'my_posted_count':  my_count([('state', '=', 'posted')]),
            'my_cancel_count':  my_count([('state', '=', 'cancel')]),
            'my_cash_count':    my_count([('receipt_method', '=', 'cash')]),
            'my_cheque_count':  my_count([('receipt_method', '=', 'cheque')]),
            'my_bank_count':    my_count([('receipt_method', '=', 'bank_transfer')]),
            'my_total_posted_amount': sum_posted([('create_uid', '=', self.env.uid)]),

            'currency_symbol': self.env.company.currency_id.symbol or '',
        }
