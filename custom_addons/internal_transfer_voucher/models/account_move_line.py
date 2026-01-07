from odoo import models, fields


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    internal_transfer_id = fields.Many2one(
        'account.internal.transfer',
        ondelete='cascade'
    )
