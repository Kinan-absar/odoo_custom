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
        domain="[('type','in',('bank','cash'))]",
        required=True
    )

    account_id = fields.Many2one(
        'account.account',
        string='Expense / Advance Account',
        domain="[('deprecated','=',False)]",
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

    payment_method = fields.Selection(
        [
            ('cash', 'Cash'),
            ('cheque', 'Cheque'),
        ],
        string="Payment Method",
        required=True,
        default='cash'
    )

    amount_in_words_ar = fields.Char(
        string="Amount in Words (Arabic)",
        compute="_compute_amount_in_words_ar"
    )

    def _compute_amount_in_words_ar(self):
        for rec in self:
            if rec.amount and rec.currency_id:
                rec.amount_in_words_ar = rec.currency_id.with_context(
                    lang='ar_001'
                ).amount_to_text(rec.amount)
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

            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.journal_id.id,
                'ref': rec.name,
                'line_ids': [
                    # Debit expense / advance
                    (0, 0, {
                        'account_id': rec.account_id.id,
                        'partner_id': rec.partner_id.id,
                        'debit': rec.amount,
                        'name': rec.name,
                    }),
                    # Credit bank / cash
                    (0, 0, {
                        'account_id': rec.journal_id.default_account_id.id,
                        'partner_id': rec.partner_id.id,
                        'credit': rec.amount,
                        'name': rec.name,
                    }),
                ],
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
