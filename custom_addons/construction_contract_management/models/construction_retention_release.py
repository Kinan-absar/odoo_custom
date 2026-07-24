from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionRetentionRelease(models.Model):
    _name = 'construction.retention.release'
    _description = 'Construction Retention Release'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Retention Release Reference',
        required=True,
        copy=False,
        default='New',
        tracking=True,
    )
    contract_id = fields.Many2one(
        'construction.contract',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    partner_id = fields.Many2one(related='contract_id.partner_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    contract_direction = fields.Selection(related='contract_id.contract_direction', store=True)

    date = fields.Date(default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(
        string='Release Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    notes = fields.Text()

    release_method = fields.Selection([
        ('journal', 'Direct Journal Entry'),
        ('invoice', 'Invoice Required'),
    ], string='Release Method', required=True, default='journal', tracking=True)

    journal_id = fields.Many2one('account.journal', string='Journal')
    retention_account_id = fields.Many2one('account.account', string='Retention Account')

    # Used only for journal method
    liquidity_account_id = fields.Many2one(
        'account.account',
        string='Liquidity Account',
        help='Bank or cash account used for direct retention release journal entry.',
    )

    move_id = fields.Many2one('account.move', string='Journal Entry / Invoice / Bill', copy=False, readonly=True)
    move_count = fields.Integer(compute='_compute_move_count')
    payment_status = fields.Selection([
        ('no_move', 'Not Posted'),
        ('not_paid', 'Not Paid'),
        ('partial', 'Partially Paid'),
        ('in_payment', 'In Payment'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], string='Payment Status', compute='_compute_payment_status', store=True)

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

    @api.depends('move_id', 'move_id.state', 'move_id.payment_state', 'release_method')
    def _compute_payment_status(self):
        for rec in self:
            move = rec.move_id
            if not move:
                rec.payment_status = 'no_move'
            elif move.state == 'cancel':
                rec.payment_status = 'cancelled'
            elif move.move_type == 'entry':
                rec.payment_status = 'paid' if move.state == 'posted' else 'not_paid'
            else:
                rec.payment_status = move.payment_state or 'not_paid'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('construction.retention.release') or 'New'
        return super().create(vals_list)

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

    def _check_accounting_setup(self):
        for rec in self:
            missing = []
            contract = rec.contract_id

            journal = rec.journal_id or contract.journal_id
            retention_account = rec.retention_account_id or contract.retention_account_id

            if not journal:
                missing.append('Journal')
            if not retention_account:
                missing.append('Retention Account')

            if rec.release_method == 'journal' and not rec.liquidity_account_id:
                missing.append('Liquidity Account')

            if missing:
                raise ValidationError(
                    'Please configure retention release accounting fields before posting:\n- ' +
                    '\n- '.join(missing)
                )

    def action_post_release(self):
        for rec in self:
            if rec.move_id:
                raise ValidationError('A journal entry or invoice/bill is already linked to this retention release.')

            rec._check_accounting_setup()

            if rec.release_method == 'journal':
                rec._create_journal_entry()
            else:
                rec._create_invoice_or_bill()

            rec.state = 'posted'

    def _create_journal_entry(self):
        self.ensure_one()

        contract = self.contract_id
        journal = self.journal_id or contract.journal_id
        retention_account = self.retention_account_id or contract.retention_account_id
        liquidity_account = self.liquidity_account_id

        line_vals = []

        if self.contract_direction == 'inbound':
            # We are receiving retained money from customer
            line_vals = [
                (0, 0, {
                    'name': f'{self.name} - Retention Release',
                    'account_id': liquidity_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'partner_id': contract.partner_id.id,
                }),
                (0, 0, {
                    'name': f'{self.name} - Retention Receivable Clearance',
                    'account_id': retention_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                    'partner_id': contract.partner_id.id,
                }),
            ]
        else:
            # We are paying retained money to subcontractor
            line_vals = [
                (0, 0, {
                    'name': f'{self.name} - Retention Payable Clearance',
                    'account_id': retention_account.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'partner_id': contract.partner_id.id,
                }),
                (0, 0, {
                    'name': f'{self.name} - Retention Release Payment',
                    'account_id': liquidity_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                    'partner_id': contract.partner_id.id,
                }),
            ]

        move_vals = {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': journal.id,
            'ref': self.name,
            'line_ids': line_vals,
        }

        move = self.env['account.move'].create(move_vals)
        self.move_id = move.id

    def _create_invoice_or_bill(self):
        self.ensure_one()

        contract = self.contract_id
        journal = self.journal_id or contract.journal_id
        retention_account = self.retention_account_id or contract.retention_account_id

        move_type = 'out_invoice' if self.contract_direction == 'inbound' else 'in_invoice'

        # No VAT. No revenue/expense recognition.
        # This is only clearing retained balance through partner document.
        invoice_line_vals = [(0, 0, {
            'name': f'{self.name} - Retention Release',
            'quantity': 1.0,
            'price_unit': self.amount,
            'account_id': retention_account.id,
            'tax_ids': [(6, 0, [])],
        })]

        move_vals = {
            'move_type': move_type,
            'partner_id': contract.partner_id.id,
            'currency_id': contract.currency_id.id,
            'invoice_date': self.date,
            'journal_id': journal.id,
            'invoice_origin': self.name,
            'ref': self.name,
            'invoice_line_ids': invoice_line_vals,
        }

        move = self.env['account.move'].create(move_vals)
        self.move_id = move.id

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise ValidationError('No journal entry or invoice/bill linked to this retention release.')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Journal Entry / Invoice / Bill',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        self.state = 'draft'
