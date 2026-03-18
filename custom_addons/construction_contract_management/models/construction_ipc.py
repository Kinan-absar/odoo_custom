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
    advance_recovery_amount = fields.Monetary(currency_field='currency_id', default=0.0)
    deduction_amount = fields.Monetary(currency_field='currency_id', default=0.0)
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
        'line_ids.cumulative_value',
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
            rec.net_amount = net
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.ipc') or 'New'
        return super().create(vals)

    def action_submit_review(self):
        self.state = 'under_review'

    def action_approve(self):
        self.state = 'approved'

    def action_done(self):
        self.state = 'done'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        self.state = 'draft'

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
                    'previous_qty': line.previous_qty,
                    'current_qty': line.current_qty,
                    'cumulative_qty': line.cumulative_qty,
                    'unit_rate': line.boq_line_id.unit_rate,
                }))

            rec.line_ids = lines_vals

    def action_approve(self):
        for rec in self:
            if rec.state != 'under_review':
                continue

            rec.state = 'approved'

            if not rec.advance_recovery_posted:
                rec.contract_id.advance_recovered += rec.advance_recovery_amount
                rec.advance_recovery_posted = True

                
class ConstructionIPCLine(models.Model):
    _name = 'construction.ipc.line'
    _description = 'Construction IPC Line'

    ipc_id = fields.Many2one('construction.ipc', required=True, ondelete='cascade')
    boq_line_id = fields.Many2one('construction.contract.boq.line', required=True)
    description = fields.Text(related='boq_line_id.description', store=True)
    currency_id = fields.Many2one(related='ipc_id.currency_id', store=True)

    previous_qty = fields.Float()
    current_qty = fields.Float()
    cumulative_qty = fields.Float()
    unit_rate = fields.Monetary(currency_field='currency_id')
    current_value = fields.Monetary(currency_field='currency_id', compute='_compute_values', store=True)
    cumulative_value = fields.Monetary(currency_field='currency_id', compute='_compute_values', store=True)

    @api.depends('current_qty', 'cumulative_qty', 'unit_rate')
    def _compute_values(self):
        for rec in self:
            rec.current_value = rec.current_qty * rec.unit_rate
            rec.cumulative_value = rec.cumulative_qty * rec.unit_rate