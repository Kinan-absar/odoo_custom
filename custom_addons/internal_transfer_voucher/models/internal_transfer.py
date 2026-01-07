from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountInternalTransfer(models.Model):
    _name = 'account.internal.transfer'
    _description = 'Internal Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

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
        required=True,
        tracking=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id,
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

    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        required=True
    )

    # ----------------------------
    # Constraints
    # ----------------------------

    @api.constrains('source_journal_id', 'destination_journal_id')
    def _check_journals(self):
        for rec in self:
            if rec.source_journal_id == rec.destination_journal_id:
                raise UserError(_("Source and destination journals must be different."))

    # ----------------------------
    # Actions
    # ----------------------------

    def action_post(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.source_journal_id.default_account_id:
                raise UserError(_("Source journal has no default account."))
            if not rec.destination_journal_id.default_account_id:
                raise UserError(_("Destination journal has no default account."))

            move = self.env['account.move'].create({
                'date': rec.date,
                'journal_id': rec.source_journal_id.id,
                'ref': rec.name,
                'line_ids': [
                    (0, 0, {
                        'account_id': rec.source_journal_id.default_account_id.id,
                        'credit': rec.amount,
                        'currency_id': rec.currency_id.id,
                    }),
                    (0, 0, {
                        'account_id': rec.destination_journal_id.default_account_id.id,
                        'debit': rec.amount,
                        'currency_id': rec.currency_id.id,
                    }),
                ]
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

    # ----------------------------
    # Sequence
    # ----------------------------

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'internal.transfer'
            ) or 'New'
        return super().create(vals)
