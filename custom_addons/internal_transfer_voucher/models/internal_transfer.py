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

    name = fields.Char(default='New', copy=False, readonly=True)

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
        string="Source Journal",
        domain="[('default_account_id', '!=', False)]",
        required=True
    )
    line_ids = fields.One2many(
        'account.internal.transfer.line',
        'transfer_id',
        string="Destination Journals"
    )

    description = fields.Text(string="Notes")
    # --------------------------------------------------
    # Bank Fees
    # --------------------------------------------------

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

    # --------------------------------------------------
    # Analytic (THE ONLY ADDITION)
    # --------------------------------------------------

    analytic_distribution = fields.Json(
        string="Analytic Distribution"
    )

    analytic_precision = fields.Integer(
        default=2,
        readonly=True
    )


    # --------------------------------------------------
    # Technical
    # --------------------------------------------------

    move_id = fields.Many2one('account.move', readonly=True, copy=False)

    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled')],
        default='draft',
        tracking=True
    )

    # --------------------------------------------------
    # Constraints
    # --------------------------------------------------

    @api.constrains(
        'line_ids',
        'amount',
        'has_bank_fees',
        'fee_amount',
        'fee_tax_id'
    )
    def _check_destination_total(self):
        for rec in self:
            if not rec.line_ids:
                continue

            destination_total = sum(rec.line_ids.mapped('amount'))

            expected_amount = rec.amount

            if rec.has_bank_fees and rec.fee_amount:
                tax_amount = 0.0
                if rec.fee_tax_id:
                    tax_amount = sum(
                        tax['amount']
                        for tax in rec.fee_tax_id.compute_all(
                            rec.fee_amount,
                            currency=rec.currency_id
                        )['taxes']
                    )
                expected_amount -= (rec.fee_amount + tax_amount)

            # Avoid float precision issues
            if not rec.currency_id.is_zero(destination_total - expected_amount):
                raise UserError(_(
                    "Destination total (%s) must equal net transfer amount (%s)."
                ) % (destination_total, expected_amount))



    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.source_journal_id.default_account_id:
                raise UserError(_("Source journal has no default account."))

            if not rec.line_ids:
                raise UserError(_("Please add at least one destination journal."))

            if rec.has_bank_fees and not rec.fee_account_id:
                raise UserError(_("Please set a bank fee account."))

            lines = []
            net_amount = rec.amount

            analytic_vals = {}
            if rec.analytic_distribution:
                analytic_vals['analytic_distribution'] = rec.analytic_distribution

            # 1️⃣ Credit source journal
            lines.append((0, 0, {
                'account_id': rec.source_journal_id.default_account_id.id,
                'credit': rec.amount,
                'name': rec.description or rec.name,
            }))

            # 2️⃣ Bank fees
            if rec.has_bank_fees and rec.fee_amount:
                lines.append((0, 0, {
                    'account_id': rec.fee_account_id.id,
                    'debit': rec.fee_amount,
                    'tax_ids': [(6, 0, rec.fee_tax_id.ids)] if rec.fee_tax_id else [],
                    'name': _('Bank Fees'),
                    **analytic_vals,
                }))

                tax_amount = sum(
                    tax['amount']
                    for tax in rec.fee_tax_id.compute_all(
                        rec.fee_amount,
                        currency=rec.currency_id
                    )['taxes']
                ) if rec.fee_tax_id else 0.0

                net_amount -= (rec.fee_amount + tax_amount)

            if net_amount <= 0:
                raise UserError(_("Net transferred amount must be greater than zero."))

            # 3️⃣ Debit multiple destination journals
            for line in rec.line_ids:
                if not line.journal_id.default_account_id:
                    raise UserError(_("One destination journal has no default account."))

                lines.append((0, 0, {
                    'account_id': line.journal_id.default_account_id.id,
                    'debit': line.amount,
                    'name': rec.description or rec.name,
                }))

            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.source_journal_id.id,
                'ref': rec.description or rec.name,
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


    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'internal.transfer'
            ) or 'New'
        return super().create(vals)

    @api.constrains('has_bank_fees', 'analytic_distribution')
    def _check_analytic_required(self):
        for rec in self:
            if rec.has_bank_fees and not rec.analytic_distribution:
                raise UserError(_("Please set Analytic Distribution for bank fees."))

    def write(self, vals):
        for rec in self:
            if rec.state == 'posted':
                allowed_fields = {'state', 'move_id'}
                if not set(vals.keys()).issubset(allowed_fields):
                    raise UserError(_("You cannot modify a posted internal transfer."))
        return super().write(vals)
    def unlink(self):
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("You cannot delete a posted internal transfer."))
        return super().unlink()

class AccountInternalTransferLine(models.Model):
    _name = 'account.internal.transfer.line'
    _description = 'Internal Transfer Destination'

    transfer_id = fields.Many2one(
        'account.internal.transfer',
        required=True,
        ondelete='cascade'
    )

    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain="[('default_account_id','!=',False)]"
    )

    amount = fields.Monetary(required=True)

    currency_id = fields.Many2one(
        related='transfer_id.currency_id',
        store=True
    )

    # ✅ CORRECT multi-create override
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            transfer_id = vals.get('transfer_id')
            if transfer_id:
                transfer = self.env['account.internal.transfer'].browse(transfer_id)
                if transfer.state == 'posted':
                    raise UserError(
                        _("You cannot add destination lines to a posted transfer.")
                    )
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            if line.transfer_id.state == 'posted':
                raise UserError(
                    _("You cannot modify destination lines of a posted transfer.")
                )
        return super().write(vals)

    def unlink(self):
        for line in self:
            if line.transfer_id.state == 'posted':
                raise UserError(
                    _("You cannot delete destination lines of a posted transfer.")
                )
        return super().unlink()
