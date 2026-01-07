from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountInternalTransfer(models.Model):
    _name = 'account.internal.transfer'
    _description = 'Internal Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    date = fields.Date(default=fields.Date.context_today, required=True)
    amount = fields.Monetary(string="Transfer Amount", required=True)
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
        domain="[('type','in',('bank','cash'))]",
        required=True
    )
    destination_journal_id = fields.Many2one(
        'account.journal',
        string="Destination Journal",
        domain="[('type','in',('bank','cash'))]",
        required=True
    )

    fee_line_ids = fields.One2many(
        'account.internal.transfer.line',
        'transfer_id'
    )


    move_id = fields.Many2one('account.move', readonly=True, copy=False)

    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled')],
        default='draft',
        tracking=True
    )

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

            lines = []
            net_amount = rec.amount

            # 1️⃣ Credit source journal (bank)
            lines.append((0, 0, {
                'account_id': rec.source_journal_id.default_account_id.id,
                'credit': rec.amount,
                'name': rec.name,
            }))

            # 2️⃣ Copy fee / expense lines EXACTLY as entered
            for fee in rec.fee_line_ids:
                if not fee.account_id:
                    raise UserError(_("Fee line must have an account."))

                line_vals = {
                    'account_id': fee.account_id.id,
                    'debit': fee.debit,
                    'tax_ids': [(6, 0, fee.tax_ids.ids)],
                    'analytic_distribution': fee.analytic_distribution,
                    'name': fee.name,
                }
                lines.append((0, 0, line_vals))

                # reduce net by fee + VAT (computed by Odoo)
                tax_amount = sum(
                    tax['amount']
                    for tax in fee.tax_ids.compute_all(
                        fee.debit,
                        currency=rec.currency_id
                    )['taxes']
                )
                net_amount -= (fee.debit + tax_amount)

            if net_amount <= 0:
                raise UserError(_("Net transferred amount must be greater than zero."))

            # 3️⃣ Debit destination journal (petty cash)
            lines.append((0, 0, {
                'account_id': rec.destination_journal_id.default_account_id.id,
                'debit': net_amount,
                'name': rec.name,
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

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'internal.transfer'
            ) or 'New'
        return super().create(vals)
