from odoo import api, fields, models


class ConstructionContractBoqLine(models.Model):
    _name = 'construction.contract.boq.line'
    _description = 'Construction Contract BOQ Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    measurement_line_ids = fields.One2many('construction.measurement.line', 'boq_line_id')
    ipc_line_ids = fields.One2many('construction.ipc.line', 'boq_line_id')
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], string='Display Type', default=False)
    section = fields.Char(string='Section')
    item_code = fields.Char(string='Item Code')
    description = fields.Text(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')

    contract_qty = fields.Float(string='Contract Qty', required=True, default=1.0)
    unit_rate = fields.Monetary(string='Unit Rate', currency_field='currency_id', required=True, default=0.0)
    total_amount = fields.Monetary(
        string='Original Amount',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
    )

    variation_qty_increase = fields.Float(
        string='Variation Increase Qty',
        compute='_compute_variation_fields',
        store=True,
    )
    variation_qty_decrease = fields.Float(
        string='Variation Decrease Qty',
        compute='_compute_variation_fields',
        store=True,
    )
    revised_qty = fields.Float(
        string='Revised Qty',
        compute='_compute_variation_fields',
        store=True,
    )
    revised_unit_rate = fields.Monetary(
        string='Revised Unit Rate',
        currency_field='currency_id',
        compute='_compute_variation_fields',
        store=True,
    )
    revised_amount = fields.Monetary(
        string='Revised Amount',
        currency_field='currency_id',
        compute='_compute_variation_fields',
        store=True,
    )
    is_omitted = fields.Boolean(
        string='Omitted',
        compute='_compute_variation_fields',
        store=True,
    )

    measured_qty = fields.Float(
        string='Measured Qty',
        compute='_compute_progress_fields',
        store=True,
    )
    certified_qty = fields.Float(
        string='Certified Qty',
        compute='_compute_progress_fields',
        store=True,
    )
    remaining_qty = fields.Float(
        string='Remaining Qty',
        compute='_compute_progress_fields',
        store=True,
    )

    @api.depends('contract_qty', 'unit_rate', 'display_type')
    def _compute_amounts(self):
        for rec in self:
            if rec.display_type:
                rec.total_amount = 0.0
            else:
                rec.total_amount = rec.contract_qty * rec.unit_rate

    @api.depends('contract_qty', 'unit_rate', 'contract_id', 'display_type')
    def _compute_variation_fields(self):
        VariationLine = self.env['construction.variation.line']

        for rec in self:
            if rec.display_type:
                rec.variation_qty_increase = 0.0
                rec.variation_qty_decrease = 0.0
                rec.revised_qty = 0.0
                rec.revised_unit_rate = 0.0
                rec.revised_amount = 0.0
                rec.is_omitted = False
                continue

            approved_lines = VariationLine.search([
                ('variation_id.contract_id', '=', rec.contract_id.id),
                ('variation_id.state', '=', 'approved'),
                ('boq_line_id', '=', rec.id),
            ])

            increase_qty = 0.0
            decrease_qty = 0.0
            revised_unit_rate = rec.unit_rate
            is_omitted = False

            for line in approved_lines:
                if line.type == 'increase':
                    increase_qty += line.variation_qty
                elif line.type == 'decrease':
                    decrease_qty += line.variation_qty
                elif line.type == 'omit':
                    is_omitted = True
                elif line.type == 'rate':
                    revised_unit_rate = line.unit_rate or revised_unit_rate

            revised_qty = rec.contract_qty + increase_qty - decrease_qty

            if is_omitted:
                revised_qty = 0.0

            rec.variation_qty_increase = increase_qty
            rec.variation_qty_decrease = decrease_qty
            rec.revised_qty = revised_qty
            rec.revised_unit_rate = revised_unit_rate
            rec.revised_amount = revised_qty * revised_unit_rate
            rec.is_omitted = is_omitted

    @api.depends(
        'contract_qty',
        'revised_qty',
        'measurement_line_ids.current_qty',
        'measurement_line_ids.measurement_id.state',
        'ipc_line_ids.current_qty',
        'ipc_line_ids.ipc_id.state',
        'display_type',
    )
    def _compute_progress_fields(self):
        for rec in self:
            if rec.display_type:
                rec.measured_qty = 0.0
                rec.certified_qty = 0.0
                rec.remaining_qty = 0.0
                continue

            approved_measurement_lines = rec.measurement_line_ids.filtered(
                lambda l: l.measurement_id.state == 'approved'
            )
            approved_ipc_lines = rec.ipc_line_ids.filtered(
                lambda l: l.ipc_id.state in ['approved', 'done']
            )

            rec.measured_qty = sum(approved_measurement_lines.mapped('current_qty'))
            rec.certified_qty = sum(approved_ipc_lines.mapped('current_qty'))

            allowed_qty = rec.revised_qty or rec.contract_qty
            rec.remaining_qty = allowed_qty - rec.certified_qty

    @api.onchange('display_type')
    def _onchange_display_type(self):
        for rec in self:
            if rec.display_type:
                rec.item_code = False
                rec.uom_id = False
                rec.contract_qty = 0.0
                rec.unit_rate = 0.0

    def name_get(self):
        result = []
        for rec in self:
            parts = []
            if rec.item_code:
                parts.append(rec.item_code)
            if rec.description:
                parts.append(rec.description)
            name = ' - '.join(parts) if parts else f'BOQ {rec.id}'
            result.append((rec.id, name))
        return result
