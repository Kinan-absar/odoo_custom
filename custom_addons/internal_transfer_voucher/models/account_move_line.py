from odoo import models, fields


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    internal_transfer_id = fields.Many2one(
        'account.internal.transfer',
        ondelete='cascade'
    )
class InternalTransferFeeLine(models.Model):
    _name = 'account.internal.transfer.line'
    _description = 'Internal Transfer Fee Line'

    transfer_id = fields.Many2one(
        'account.internal.transfer',
        required=True,
        ondelete='cascade'
    )

    account_id = fields.Many2one('account.account', required=True)
    debit = fields.Monetary(required=True)
    tax_ids = fields.Many2many('account.tax')
    analytic_distribution = fields.Json()
    name = fields.Char()
    currency_id = fields.Many2one(
        'res.currency',
        related='transfer_id.currency_id',
        store=True
    )
