from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionAdvance(models.Model):
    _name = 'construction.advance'
    _description = 'Construction Advance Payment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Advance Reference', required=True, copy=False, default='New', tracking=True)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    partner_id = fields.Many2one(related='contract_id.partner_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    contract_direction = fields.Selection(related='contract_id.contract_direction', store=True)

    date = fields.Date(default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(string='Advance Amount', currency_field='currency_id', required=True, tracking=True)
    tax_id = fields.Many2one('account.tax', string='VAT Tax')
    tax_amount = fields.Monetary(string='Tax Amount', currency_field='currency_id', compute='_compute_totals', store=True)
    total_amount = fields.Monetary(string='Total Amount', currency_field='currency_id', compute='_compute_totals', store=True)

    journal_id = fields.Many2one('account.journal', string='Journal')
    advance_account_id = fields.Many2one('account.account', string='Advance Account')

    move_id = fields.Many2one('account.move', string='Invoice/Bill', copy=False, readonly=True)
    move_count = fields.Integer(compute='_compute_move_count')
    payment_status = fields.Selection([
        ('no_move', 'Not Invoiced'),
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

    @api.depends('amount', 'tax_id')
    def _compute_totals(self):
        for rec in self:
            tax_amount = 0.0
            if rec.tax_id and rec.amount:
                taxes = rec.tax_id.compute_all(
                    rec.amount,
                    currency=rec.currency_id,
                    quantity=1.0,
                    product=None,
                    partner=rec.partner_id,
                )
                tax_amount = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
            rec.tax_amount = tax_amount
            rec.total_amount = (rec.amount or 0.0) + tax_amount

    def _compute_move_count(self):
        for rec in self:
            rec.move_count = 1 if rec.move_id else 0

    @api.depends('move_id', 'move_id.state', 'move_id.payment_state')
    def _compute_payment_status(self):
        for rec in self:
            move = rec.move_id
            if not move:
                rec.payment_status = 'no_move'
            elif move.state == 'cancel':
                rec.payment_status = 'cancelled'
            else:
                rec.payment_status = move.payment_state or 'not_paid'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('construction.advance') or 'New'
        return super().create(vals_list)

    def _check_accounting_setup(self):
        for rec in self:
            missing = []
            journal = rec.journal_id or rec.contract_id.journal_id
            tax = rec.tax_id or rec.contract_id.tax_id
            advance_account = rec.advance_account_id or rec.contract_id.advance_account_id

            if not journal:
                missing.append('Journal')
            if not advance_account:
                missing.append('Advance Account')
            if not tax:
                missing.append('VAT Tax')

            if missing:
                raise ValidationError(
                    'Please configure advance accounting fields before creating invoice/bill:\n- ' +
                    '\n- '.join(missing)
                )

    def action_create_move(self):
        for rec in self:
            if rec.move_id:
                raise ValidationError('Invoice/Bill already created for this advance.')

            if rec.amount <= 0:
                raise ValidationError('Advance amount must be greater than zero.')

            rec._check_accounting_setup()

            contract = rec.contract_id
            journal = rec.journal_id or contract.journal_id
            tax = rec.tax_id or contract.tax_id
            advance_account = rec.advance_account_id or contract.advance_account_id

            move_type = 'out_invoice' if rec.contract_direction == 'inbound' else 'in_invoice'

            move_vals = {
                'move_type': move_type,
                'partner_id': contract.partner_id.id,
                'currency_id': contract.currency_id.id,
                'invoice_date': rec.date,
                'journal_id': journal.id,
                'invoice_origin': rec.name,
                'ref': rec.name,
                'invoice_line_ids': [(0, 0, {
                    'name': f'{rec.name} - Advance Payment',
                    'quantity': 1.0,
                    'price_unit': rec.amount,
                    'account_id': advance_account.id,
                    'tax_ids': [(6, 0, tax.ids)],
                })],
            }

            move = self.env['account.move'].create(move_vals)
            rec.move_id = move.id
            rec.state = 'posted'

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise ValidationError('No invoice/bill linked to this advance.')

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
