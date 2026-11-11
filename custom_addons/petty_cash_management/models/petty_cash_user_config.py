from odoo import models, fields, api
from odoo.exceptions import ValidationError

class PettyCashUserConfig(models.Model):
    _name = 'petty.cash.user.config'
    _description = 'Petty Cash User Configuration'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    petty_cash_account_id = fields.Many2one(
        'account.account',
        string='Petty Cash Account',
        required=True
    )

    input_vat_account_id = fields.Many2one(
        'account.account',
        string='Input VAT Account',
        required=True
    )

    petty_cash_journal_id = fields.Many2one(
        'account.journal',
        string='Petty Cash Journal',
        domain="[('type', '=', 'general')]",
        required=True
    )

    _sql_constraints = [
        (
            'unique_partner_company',
            'unique(partner_id, company_id)',
            'A petty cash configuration already exists for this partner in this company.'
        )
    ]