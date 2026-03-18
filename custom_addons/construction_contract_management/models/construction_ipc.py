from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionIPC(models.Model):
    _name = 'construction.ipc'
    _description = 'Construction IPC'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, default='New')
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    measurement_id = fields.Many2one('construction.measurement', string='Measurement', tracking=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    contract_direction = fields.Selection(related='contract_id.contract_direction', store=True)

    ipc_date = fields.Date(default=fields.Date.context_today, tracking=True)
    period_from = fields.Date()
    period_to = fields.Date()

    line_ids = fields.One2many('construction.ipc.line', 'ipc_id', string='IPC Lines')

    previous_certified_value = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    current_work_value = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    cumulative_certified_value = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    retention_amount = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    advance_recovery_amount = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    deduction_amount = fields.Monetary(currency_field='currency_id', default=0.0)
    vat_amount = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    gross_with_vat = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)
    net_amount = fields.Monetary(currency_field='currency_id', compute='_compute_amounts', store=True)

    advance_recovery_posted = fields.Boolean(default=False)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    @api.depends(
        'line_ids.current_value',
        'contract_id.retention_percent',
        'contract_id.advance_percent',
        'contract_id.advance_amount',
        'contract_id.advance_recovered',
        'contract_id.vat_percent',
        'deduction_amount',
    )
    def _compute_amounts(self):
        for rec in self:
            current_work = sum(rec.line_ids.mapped('current_value'))

            previous_ipcs = self.env['construction.ipc'].search([
                ('contract_id', '=', rec.contract_id.id),
                ('id', '!=', rec.id),
                ('state', 'in', ['approved', 'done'])
            ])

            previous_certified_value = sum(previous_ipcs.mapped('current_work_value'))
            cumulative_certified_value = previous_certified_value + current_work

            advance_percent = (rec.contract_id.advance_percent or 0.0) / 100.0
            retention_percent = (rec.contract_id.retention_percent or 0.0) / 100.0
            vat_percent = (rec.contract_id.vat_percent or 0.0) / 100.0

            proposed_recovery = current_work * advance_percent
            remaining_advance = max(
                (rec.contract_id.advance_amount or 0.0) - (rec.contract_id.advance_recovered or 0.0),
                0.0
            )
            actual_recovery = min(proposed_recovery, remaining_advance)

            taxable_base = current_work - actual_recovery
            vat_amount = taxable_base * vat_percent
            gross_with_vat = taxable_base + vat_amount

            retention = current_work * retention_percent
            net = gross_with_vat - retention - (rec.deduction_amount or 0.0)

            rec.previous_certified_value = previous_certified_value
            rec.current_work_value = current_work
            rec.cumulative_certified_value = cumulative_certified_value
            rec.advance_recovery_amount = actual_recovery
            rec.retention_amount = retention
            rec.vat_amount = vat_amount
            rec.gross_with_vat = gross_with_vat
            rec.net_amount = net

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.ipc') or 'New'
        return super().create(vals)

    def action_submit_review(self):
        self.state = 'under_review'

    def action_approve(self):
        for rec in self:
            if rec.state != 'under_review':
                continue

            rec.state = 'approved'

            if not rec.advance_recovery_posted:
                rec.contract_id.advance_recovered += rec.advance_recovery_amount
                rec.advance_recovery_posted = True

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        for rec in self:
            if rec.advance_recovery_posted:
                rec.contract_id.advance_recovered -= rec.advance_recovery_amount
                rec.advance_recovery_posted = False
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.advance_recovery_posted:
                rec.contract_id.advance_recovered -= rec.advance_recovery_amount
                rec.advance_recovery_posted = False
            rec.state = 'draft'

    def action_load_from_measurement(self):
        for rec in self:
            if not rec.measurement_id:
                continue

            if rec.state != 'draft':
                continue

            if rec.line_ids:
                raise ValidationError("IPC already has lines. Please clear them first.")

            if rec.measurement_id.state != 'approved':
                raise ValidationError("Only approved measurements can be loaded.")

            existing_ipc = self.env['construction.ipc'].search([
                ('measurement_id', '=', rec.measurement_id.id),
                ('id', '!=', rec.id),
                ('state', 'in', ['approved', 'done'])
            ], limit=1)

            if existing_ipc:
                raise ValidationError("This measurement is already used in another IPC.")

            lines_vals = []
            for line in rec.measurement_id.line_ids:
                lines_vals.append((0, 0, {
                    'boq_line_id': line.boq_line_id.id,
                    'measurement_line_id': line.id,
                    'previous_qty': line.previous_qty,
                    'current_qty': line.current_qty,
                    'cumulative_qty': line.cumulative_qty,
                    'unit_rate': line.boq_line_id.revised_unit_rate or line.boq_line_id.unit_rate,
                }))

            rec.line_ids = lines_vals


class ConstructionIPCLine(models.Model):
    _name = 'construction.ipc.line'
    _description = 'Construction IPC Line'

    ipc_id = fields.Many2one('construction.ipc', required=True, ondelete='cascade')
    boq_line_id = fields.Many2one('construction.contract.boq.line', required=True)
    measurement_line_id = fields.Many2one('construction.measurement.line', string='Measurement Line')
    description = fields.Text(related='boq_line_id.description', store=True)
    currency_id = fields.Many2one(related='ipc_id.currency_id', store=True)

    previous_qty = fields.Float()
    current_qty = fields.Float()
    cumulative_qty = fields.Float()
    allowed_qty = fields.Float(compute='_compute_allowed_qty', store=True)
    remaining_qty = fields.Float(compute='_compute_remaining_qty', store=True)

    unit_rate = fields.Monetary(currency_field='currency_id')
    current_value = fields.Monetary(currency_field='currency_id', compute='_compute_values', store=True)
    cumulative_value = fields.Monetary(currency_field='currency_id', compute='_compute_values', store=True)

    @api.depends('boq_line_id.revised_qty', 'boq_line_id.contract_qty')
    def _compute_allowed_qty(self):
        for rec in self:
            rec.allowed_qty = rec.boq_line_id.revised_qty or rec.boq_line_id.contract_qty

    @api.depends('allowed_qty', 'cumulative_qty')
    def _compute_remaining_qty(self):
        for rec in self:
            rec.remaining_qty = rec.allowed_qty - rec.cumulative_qty

    @api.depends('current_qty', 'cumulative_qty', 'unit_rate')
    def _compute_values(self):
        for rec in self:
            rec.current_value = rec.current_qty * rec.unit_rate
            rec.cumulative_value = rec.cumulative_qty * rec.unit_rate

    @api.constrains('current_qty', 'previous_qty', 'cumulative_qty', 'boq_line_id', 'measurement_line_id')
    def _check_ipc_quantities(self):
        for rec in self:
            if rec.current_qty < 0:
                raise ValidationError('IPC current quantity cannot be negative.')

            allowed_qty = rec.boq_line_id.revised_qty or rec.boq_line_id.contract_qty
            cumulative_qty = rec.cumulative_qty or (rec.previous_qty + rec.current_qty)

            if cumulative_qty > allowed_qty:
                raise ValidationError(
                    f'IPC quantity exceeds allowed BOQ quantity.\n'
                    f'Allowed Qty: {allowed_qty}\n'
                    f'Previous Qty: {rec.previous_qty}\n'
                    f'Current Qty: {rec.current_qty}\n'
                    f'Cumulative Qty: {cumulative_qty}'
                )

            if rec.measurement_line_id:
                measured_current = rec.measurement_line_id.current_qty
                measured_cumulative = rec.measurement_line_id.cumulative_qty

                if rec.current_qty > measured_current:
                    raise ValidationError(
                        f'IPC current quantity cannot exceed measured current quantity.\n'
                        f'Measured Current Qty: {measured_current}\n'
                        f'IPC Current Qty: {rec.current_qty}'
                    )

                if cumulative_qty > measured_cumulative:
                    raise ValidationError(
                        f'IPC cumulative quantity cannot exceed measured cumulative quantity.\n'
                        f'Measured Cumulative Qty: {measured_cumulative}\n'
                        f'IPC Cumulative Qty: {cumulative_qty}'
                    )