from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountInternalTransfer(models.Model):
    _name = 'account.internal.transfer'
    _description = 'Internal Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # --------------------------------------------------
    # Basic Fields
    # --------------------------------------------------

    name = fields.Char(
        default='New',
        copy=False,
        readonly=True
    )

    date = fields.Date(
        default=fields.Date.context_today,
        required=True
    )

    amount = fields.Monetary(
        string="Transfer Amount",
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

    source_journal_id = fields.Many2one(
        'account.journal',
        string='Source Journal',
        domain="[('type','in',('bank','cash'))]",
        required=True
    )

    destination_journal_id = fields.Many2one(
        'account.journal',
        string='Destination Journal',
        domain="[('type','in',('bank','cash'))]",
        required=True
    )

    move_id = fields.Many2one(
        'account.move',
        readonly=True,
        copy=False
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled')
    ], default='draft', tracking=True)

    # --------------------------------------------------
    # Bank Fees + VAT
    # --------------------------------------------------

    has_bank_fees = fields.Boolean(string="Bank Fees")

    fee_amount = fields.Monetary(
        string="Bank Fee Amount"
    )

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


    # --------------------------------------------------
    # Constraints
    # --------------------------------------------------

    @api.constrains('source_journal_id', 'destination_journal_id')
    def _check_journals(self):
        for rec in self:
            if rec.source_journal_id == rec.destination_journal_id:
                raise UserError(_("Source and destination journals must be different."))

    @api.constrains('fee_amount')
    def _check_fee_amount(self):
        for rec in self:
            if rec.has_bank_fees and rec.fee_amount <= 0:
                raise UserError(_("Bank fee amount must be greater than zero."))

    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.source_journal_id.default_account_id:
                raise UserError(_("Source journal has no default account."))

            if not rec.destination_journal_id.default_account_id:
                raise UserError(_("Destination journal has no default account."))

            if rec.has_bank_fees and not rec.fee_account_id:
                raise UserError(_("Please set a bank fee account."))

            lines = []
            net_amount = rec.amount

            # 1️⃣ Credit bank (gross)
            lines.append((0, 0, {
                'account_id': rec.source_journal_id.default_account_id.id,
                'credit': rec.amount,
            }))

            # 2️⃣ Bank fee (with VAT via tax_ids)
            if rec.has_bank_fees:
                if not rec.fee_account_id:
                    raise UserError(_("Please set a bank fee account."))

                fee_line = {
                    'account_id': rec.fee_account_id.id,
                    'debit': rec.fee_amount,
                    'tax_ids': [(6, 0, rec.fee_tax_id.ids)] if rec.fee_tax_id else [],
                }
                lines.append((0, 0, fee_line))

                # net = gross - fee - VAT (Odoo will compute VAT)
                tax_amount = sum(
                    rec.fee_tax_id.compute_all(
                        rec.fee_amount,
                        currency=rec.currency_id
                    )['taxes'][i]['amount']
                    for i in range(len(rec.fee_tax_id.ids))
                ) if rec.fee_tax_id else 0.0

                net_amount -= (rec.fee_amount + tax_amount)

            # 3️⃣ Debit destination (net)
            lines.append((0, 0, {
                'account_id': rec.destination_journal_id.default_account_id.id,
                'debit': net_amount,
            }))


            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.source_journal_id.id,
                'ref': rec.name,
                'line_ids': lines,
            })

            move.action_post()

            rec.move_id = move.id
            rec.state = 'posted'

    def action_cancel(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                rec.move_id.button_draft()
                rec.move_id.button_cancel()
            rec.state = 'cancel'

    # --------------------------------------------------
    # Sequence
    # --------------------------------------------------

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'internal.transfer'
            ) or 'New'
        return super().create(vals)
