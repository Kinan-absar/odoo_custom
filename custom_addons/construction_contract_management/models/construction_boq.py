from odoo import api, fields, models


class ConstructionContractBoqLine(models.Model):
    _name = 'construction.contract.boq.line'
    _description = 'Construction Contract BOQ Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)

    section = fields.Char(string='Section')
    item_code = fields.Char(string='Item Code')
    description = fields.Text(string='Description', required=True)
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')
    contract_qty = fields.Float(string='Contract Qty', required=True, default=1.0)
    unit_rate = fields.Monetary(string='Unit Rate', currency_field='currency_id', required=True, default=0.0)
    total_amount = fields.Monetary(string='Total Amount', currency_field='currency_id', compute='_compute_amounts', store=True)

    measured_qty = fields.Float(string='Measured Qty', compute='_compute_progress_fields', store=True)
    certified_qty = fields.Float(string='Certified Qty', compute='_compute_progress_fields', store=True)
    remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_progress_fields', store=True)

    @api.depends('contract_qty', 'unit_rate')
    def _compute_amounts(self):
        for rec in self:
            rec.total_amount = rec.contract_qty * rec.unit_rate

    @api.depends('contract_qty')
    def _compute_progress_fields(self):
        for rec in self:
            measurement_lines = self.env['construction.measurement.line'].search([
                ('boq_line_id', '=', rec.id),
                ('measurement_id.state', '=', 'approved')
            ])

            ipc_lines = self.env['construction.ipc.line'].search([
                ('boq_line_id', '=', rec.id),
                ('ipc_id.state', 'in', ['approved', 'done'])
            ])

            rec.measured_qty = sum(measurement_lines.mapped('current_qty'))
            rec.certified_qty = sum(ipc_lines.mapped('current_qty'))
            rec.remaining_qty = rec.contract_qty - rec.certified_qty