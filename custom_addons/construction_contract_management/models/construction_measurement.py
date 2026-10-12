from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionMeasurement(models.Model):
    _name = 'construction.measurement'
    _description = 'Construction Measurement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, default='New')
    contract_sequence = fields.Integer(string='Contract Sequence', copy=False, readonly=True, index=True)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    contract_order_id = fields.Many2one(
        'construction.contract.order', string='Contract Order / Sales Order', tracking=True,
        domain="[('contract_id', '=', contract_id)]",
        help='Selects the independent Sales Order scope whose BOQ will be measured.',
    )
    sale_order_id = fields.Many2one(related='contract_order_id.sale_order_id', string='Source Sales Order', store=True, readonly=True)
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

    def _contract_sequence_starts(self, contract_ids):
        """Return the last used per-contract number, locking contracts for safe allocation."""
        starts = {}
        for contract_id in sorted(set(contract_ids)):
            self.env.cr.execute(
                "SELECT id FROM construction_contract WHERE id = %s FOR UPDATE",
                [contract_id],
            )
            self.env.cr.execute(
                """
                SELECT COALESCE(MAX(contract_sequence), 0), COUNT(*)
                  FROM construction_measurement
                 WHERE contract_id = %s
                """,
                [contract_id],
            )
            max_sequence, record_count = self.env.cr.fetchone()
            # Legacy records have contract_sequence = 0. Their count establishes
            # the starting point without renumbering historical documents.
            starts[contract_id] = max(max_sequence or 0, record_count or 0)
        return starts

    @api.model_create_multi
    def create(self, vals_list):
        contract_ids = [vals.get('contract_id') for vals in vals_list if vals.get('contract_id')]
        next_by_contract = self._contract_sequence_starts(contract_ids) if contract_ids else {}

        for vals in vals_list:
            contract_id = vals.get('contract_id')
            if contract_id and not vals.get('contract_sequence'):
                next_by_contract[contract_id] = next_by_contract.get(contract_id, 0) + 1
                vals['contract_sequence'] = next_by_contract[contract_id]
            if vals.get('name', 'New') == 'New' and vals.get('contract_sequence'):
                vals['name'] = f"MS/{fields.Date.to_date(vals.get('date') or fields.Date.context_today(self)).year}/{vals['contract_sequence']:04d}"
        return super().create(vals_list)

    def _get_report_base_filename(self):
        self.ensure_one()
        return f"Measurement_{self.name}"

    def _recompute_contract_progress(self):
        for rec in self:
            contract = rec.contract_id
            if contract:
                contract.boq_line_ids._compute_progress_fields()
                contract._compute_summary_amounts()

    def action_submit(self):
        self.state = 'submitted'

    def action_check(self):
        self.state = 'checked'

    def action_approve(self):
        self.state = 'approved'
        self._recompute_contract_progress()

    def action_reject(self):
        self.state = 'rejected'

    def action_reset_to_draft(self):
        self.state = 'draft'
        self._recompute_contract_progress()

    def action_load_boq_lines(self):
        for rec in self:
            if rec.state != 'draft':
                continue

            if not rec.contract_id:
                continue
            if rec.contract_id.contract_order_ids and not rec.contract_order_id:
                raise ValidationError('Select a Contract Order / Sales Order before loading BOQ lines.')

            rec.line_ids.unlink()

            lines = []
            boq_source = rec.contract_order_id.boq_line_ids if rec.contract_order_id else rec.contract_id.boq_line_ids
            for boq in boq_source:
                approved_lines = self.env['construction.measurement.line'].search([
                    ('boq_line_id', '=', boq.id),
                    ('measurement_id.contract_id', '=', rec.contract_id.id),
                    ('measurement_id.contract_order_id', '=', rec.contract_order_id.id if rec.contract_order_id else False),
                    ('measurement_id.state', '=', 'approved'),
                    ('measurement_id', '!=', rec.id),
                ])

                previous_qty = sum(approved_lines.mapped('current_qty'))

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
        domain="[('contract_id', '=', parent.contract_id), '|', ('contract_order_id', '=', parent.contract_order_id), ('contract_order_id', '=', False)]",
    )
    display_type = fields.Selection(
        related='boq_line_id.display_type',
        store=True,
        readonly=True
    )
    description = fields.Text(related='boq_line_id.description', store=True)
    unit_rate = fields.Monetary(related='boq_line_id.unit_rate', store=True)
    currency_id = fields.Many2one(related='measurement_id.contract_id.currency_id', store=True)

    previous_qty = fields.Float(string='Previous Qty')
    current_qty = fields.Float(string='Current Qty')
    cumulative_qty = fields.Float(string='Cumulative Qty', compute='_compute_cumulative_qty', store=True)
    allowed_qty = fields.Float(string='Allowed Qty', compute='_compute_allowed_qty', store=True)
    remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_remaining_qty', store=True)
    previous_percent = fields.Float(string='Previous %', compute='_compute_progress_percentages', store=True)
    current_percent = fields.Float(string='Current %', compute='_compute_progress_percentages', store=True)
    cumulative_percent = fields.Float(string='Total %', compute='_compute_progress_percentages', store=True)
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

    @api.depends('allowed_qty', 'previous_qty', 'current_qty', 'cumulative_qty')
    def _compute_progress_percentages(self):
        for rec in self:
            allowed_qty = rec.allowed_qty or 0.0
            if allowed_qty:
                rec.previous_percent = (rec.previous_qty / allowed_qty) * 100.0
                rec.current_percent = (rec.current_qty / allowed_qty) * 100.0
                rec.cumulative_percent = (rec.cumulative_qty / allowed_qty) * 100.0
            else:
                rec.previous_percent = 0.0
                rec.current_percent = 0.0
                rec.cumulative_percent = 0.0

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
