from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionRetentionRelease(models.Model):
    _name = 'construction.retention.release'
    _description = 'Construction Retention Release'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Retention Release Reference', required=True, copy=False, default='New', tracking=True)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    partner_id = fields.Many2one(related='contract_id.partner_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    contract_direction = fields.Selection(related='contract_id.contract_direction', store=True)

    date = fields.Date(default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(string='Release Amount', currency_field='currency_id', required=True, tracking=True)
    notes = fields.Text()

    journal_id = fields.Many2one('account.journal', string='Journal')
    retention_account_id = fields.Many2one('account.account', string='Retention Account')
    work_account_id = fields.Many2one('account.account', string='Release Account')
    tax_id = fields.Many2one('account.tax', string='VAT Tax')

    move_id = fields.Many2one('account.move', string='Invoice/Bill', copy=False, readonly=True)
    move_count = fields.Integer(compute='_compute_move_count')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    available_retention = fields.Monetary(
        string='Available Retention',
        currency_field='currency_id',
        compute='_compute_available_retention',
        store=True,
    )

    @api.depends('contract_id.retention_balance')
    def _compute_available_retention(self):
        for rec in self:
            rec.available_retention = rec.contract_id.retention_balance

    def _compute_move_count(self):
        for rec in self:
            rec.move_count = 1 if rec.move_id else 0

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.retention.release') or 'New'
        return super().create(vals)

    def _check_accounting_setup(self):
        for rec in self:
            missing = []
            contract = rec.contract_id

            journal = rec.journal_id or contract.journal_id
            retention_account = rec.retention_account_id or contract.retention_account_id
            work_account = rec.work_account_id or contract.work_account_id

            if not journal:
                missing.append('Journal')
            if not retention_account:
                missing.append('Retention Account')
            if not work_account:
                missing.append('Release Account')

            if missing:
                raise ValidationError(
                    'Please configure retention release accounting fields before creating invoice/bill:\n- ' +
                    '\n- '.join(missing)
                )

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('Release amount must be greater than zero.')
            if rec.amount > rec.contract_id.retention_balance:
                raise ValidationError(
                    f'Release amount cannot exceed available retention balance.\n'
                    f'Available Retention: {rec.contract_id.retention_balance}\n'
                    f'Release Amount: {rec.amount}'
                )

    def action_create_move(self):
        for rec in self:
            if rec.move_id:
                raise ValidationError('Invoice/Bill already created for this retention release.')

            rec._check_accounting_setup()

            contract = rec.contract_id
            journal = rec.journal_id or contract.journal_id
            retention_account = rec.retention_account_id or contract.retention_account_id
            work_account = rec.work_account_id or contract.work_account_id

            move_type = 'out_invoice' if rec.contract_direction == 'inbound' else 'in_invoice'

            invoice_line_vals = [
                (0, 0, {
                    'name': f'{rec.name} - Retention Release',
                    'quantity': 1.0,
                    'price_unit': rec.amount,
                    'account_id': work_account.id,
                    'tax_ids': [(6, 0, [])],
                }),
                (0, 0, {
                    'name': f'{rec.name} - Retention Settlement',
                    'quantity': 1.0,
                    'price_unit': -rec.amount,
                    'account_id': retention_account.id,
                    'tax_ids': [(6, 0, [])],
                }),
            ]

            move_vals = {
                'move_type': move_type,
                'partner_id': contract.partner_id.id,
                'currency_id': contract.currency_id.id,
                'invoice_date': rec.date,
                'journal_id': journal.id,
                'invoice_origin': rec.name,
                'ref': rec.name,
                'invoice_line_ids': invoice_line_vals,
            }

            move = self.env['account.move'].create(move_vals)
            rec.move_id = move.id
            rec.state = 'posted'

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise ValidationError('No invoice/bill linked to this retention release.')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice/Bill',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        self.state = 'draft'