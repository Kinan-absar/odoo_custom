from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionMeasurement(models.Model):
    _name = 'construction.measurement'
    _description = 'Construction Measurement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, default='New')
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)

    date = fields.Date(default=fields.Date.context_today, tracking=True)
    period_from = fields.Date()
    period_to = fields.Date()
    prepared_by = fields.Many2one('res.users', string='Prepared By', default=lambda self: self.env.user)
    checked_by = fields.Many2one('res.users', string='Checked By')

    line_ids = fields.One2many('construction.measurement.line', 'measurement_id', string='Measurement Lines')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('checked', 'Checked'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.measurement') or 'New'
        return super().create(vals)

    def action_submit(self):
        self.state = 'submitted'

    def action_check(self):
        self.state = 'checked'

    def action_approve(self):
        self.state = 'approved'

    def action_reject(self):
        self.state = 'rejected'

    def action_reset_to_draft(self):
        self.state = 'draft'

    def action_load_boq_lines(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.contract_id:
                continue

            rec.line_ids.unlink()

            lines = []
            for boq in rec.contract_id.boq_line_ids:
                last_line = self.env['construction.measurement.line'].search([
                    ('boq_line_id', '=', boq.id),
                    ('measurement_id.contract_id', '=', rec.contract_id.id),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', rec.id),
                ], order='id desc', limit=1)

                previous_qty = last_line.cumulative_qty if last_line else 0.0

                lines.append((0, 0, {
                    'boq_line_id': boq.id,
                    'previous_qty': previous_qty,
                    'current_qty': 0.0,
                }))

            rec.line_ids = lines


class ConstructionMeasurementLine(models.Model):
    _name = 'construction.measurement.line'
    _description = 'Construction Measurement Line'

    measurement_id = fields.Many2one('construction.measurement', required=True, ondelete='cascade')
    boq_line_id = fields.Many2one(
        'construction.contract.boq.line',
        required=True,
        domain="[('contract_id', '=', parent.contract_id)]",
    )
    description = fields.Text(related='boq_line_id.description', store=True)
    unit_rate = fields.Monetary(related='boq_line_id.unit_rate', store=True)
    currency_id = fields.Many2one(related='measurement_id.contract_id.currency_id', store=True)

    previous_qty = fields.Float(string='Previous Qty')
    current_qty = fields.Float(string='Current Qty')
    cumulative_qty = fields.Float(string='Cumulative Qty', compute='_compute_cumulative_qty', store=True)
    allowed_qty = fields.Float(string='Allowed Qty', compute='_compute_allowed_qty', store=True)
    remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_remaining_qty', store=True)
    remarks = fields.Char(string='Remarks', help='Notes or comments for this measurement line')

    @api.depends('previous_qty', 'current_qty')
    def _compute_cumulative_qty(self):
        for rec in self:
            rec.cumulative_qty = rec.previous_qty + rec.current_qty

    @api.depends('boq_line_id.revised_qty', 'boq_line_id.contract_qty')
    def _compute_allowed_qty(self):
        for rec in self:
            rec.allowed_qty = rec.boq_line_id.revised_qty or rec.boq_line_id.contract_qty

    @api.depends('allowed_qty', 'cumulative_qty')
    def _compute_remaining_qty(self):
        for rec in self:
            rec.remaining_qty = rec.allowed_qty - rec.cumulative_qty

    @api.constrains('current_qty', 'previous_qty', 'boq_line_id')
    def _check_current_qty(self):
        for rec in self:
            if rec.current_qty < 0:
                raise ValidationError('Current quantity cannot be negative.')

            allowed_qty = rec.boq_line_id.revised_qty or rec.boq_line_id.contract_qty
            cumulative_qty = rec.previous_qty + rec.current_qty

            if cumulative_qty > allowed_qty:
                raise ValidationError(
                    f'Measured quantity exceeds allowed BOQ quantity.\n'
                    f'Allowed Qty: {allowed_qty}\n'
                    f'Previous Qty: {rec.previous_qty}\n'
                    f'Current Qty: {rec.current_qty}\n'
                    f'Cumulative Qty: {cumulative_qty}'
                )