from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ConstructionVariation(models.Model):
    _name = 'construction.variation'
    _description = 'Construction Variation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default='New', copy=False, required=True)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True)
    date = fields.Date(default=fields.Date.context_today, tracking=True)
    description = fields.Text()

    line_ids = fields.One2many('construction.variation.line', 'variation_id', string='Variation Lines')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    total_amount = fields.Monetary(
        string='Variation Amount',
        currency_field='currency_id',
        compute='_compute_total_amount',
        store=True,
    )

    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.variation') or 'New'
        return super().create(vals)

    def _get_report_base_filename(self):
        self.ensure_one()
        return f"Variation_{self.name}"

    @api.depends('line_ids.amount')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped('amount'))

    def _refresh_contract_boq(self):
        for rec in self:
            boq_lines = rec.contract_id.boq_line_ids
            boq_lines._compute_variation_fields()
            boq_lines._compute_progress_fields()
            rec.contract_id._compute_revised_amount()

    def _sync_new_item_boq_lines(self):
        BoqLine = self.env['construction.contract.boq.line']

        for rec in self:
            if rec.state == 'approved':
                for line in rec.line_ids.filtered(lambda l: l.type == 'new'):
                    if line.created_boq_line_id:
                        line.created_boq_line_id.write(line._prepare_new_boq_line_vals())
                    else:
                        created_boq = BoqLine.create(line._prepare_new_boq_line_vals())
                        line.created_boq_line_id = created_boq.id
            else:
                for line in rec.line_ids.filtered(lambda l: l.type == 'new' and l.created_boq_line_id):
                    line.created_boq_line_id.unlink()
                    line.created_boq_line_id = False

    def action_submit(self):
        self.state = 'submitted'

    def action_approve(self):
        self.state = 'approved'
        self._sync_new_item_boq_lines()
        self._refresh_contract_boq()

    def action_reject(self):
        self.state = 'rejected'
        self._sync_new_item_boq_lines()
        self._refresh_contract_boq()

    def action_reset_to_draft(self):
        self.state = 'draft'
        self._sync_new_item_boq_lines()
        self._refresh_contract_boq()


class ConstructionVariationLine(models.Model):
    _name = 'construction.variation.line'
    _description = 'Construction Variation Line'

    variation_id = fields.Many2one('construction.variation', required=True, ondelete='cascade')
    contract_id = fields.Many2one(related='variation_id.contract_id', store=True)
    currency_id = fields.Many2one(related='variation_id.currency_id', store=True)

    boq_line_id = fields.Many2one(
        'construction.contract.boq.line',
        string='BOQ Line',
        domain="[('contract_id', '=', contract_id)]"
    )
    created_boq_line_id = fields.Many2one(
        'construction.contract.boq.line',
        string='Created BOQ Line',
        copy=False,
        readonly=True,
    )

    type = fields.Selection([
        ('increase', 'Quantity Increase'),
        ('decrease', 'Quantity Decrease'),
        ('new', 'New Item'),
        ('omit', 'Omit Item'),
        ('rate', 'Rate Change'),
    ], required=True)

    
    item_code = fields.Char(string='Item Code')
    description = fields.Text()
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure')

    unit_rate = fields.Monetary(string='Unit Rate', currency_field='currency_id')
    original_qty = fields.Float(string='Original Qty', compute='_compute_original_qty', store=True)
    variation_qty = fields.Float(string='Variation Qty')
    revised_qty = fields.Float(string='Revised Qty', compute='_compute_revised_qty', store=True)

    amount = fields.Monetary(
        string='Impact Amount',
        compute='_compute_amount',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('boq_line_id', 'type')
    def _compute_original_qty(self):
        for rec in self:
            if rec.type == 'new':
                rec.original_qty = 0.0
            else:
                rec.original_qty = rec.boq_line_id.contract_qty if rec.boq_line_id else 0.0

    @api.depends('original_qty', 'variation_qty', 'type')
    def _compute_revised_qty(self):
        for rec in self:
            if rec.type == 'increase':
                rec.revised_qty = rec.original_qty + rec.variation_qty
            elif rec.type == 'decrease':
                rec.revised_qty = rec.original_qty - rec.variation_qty
            elif rec.type == 'omit':
                rec.revised_qty = 0.0
            elif rec.type == 'new':
                rec.revised_qty = rec.variation_qty
            elif rec.type == 'rate':
                rec.revised_qty = rec.original_qty
            else:
                rec.revised_qty = rec.original_qty

    @api.depends('variation_qty', 'unit_rate', 'type', 'original_qty', 'boq_line_id.unit_rate')
    def _compute_amount(self):
        for rec in self:
            if rec.type == 'increase':
                rec.amount = rec.variation_qty * rec.unit_rate
            elif rec.type == 'decrease':
                rec.amount = -1 * rec.variation_qty * rec.unit_rate
            elif rec.type == 'omit':
                rate = rec.unit_rate or (rec.boq_line_id.unit_rate if rec.boq_line_id else 0.0)
                qty = rec.original_qty
                rec.amount = -1 * qty * rate
            elif rec.type == 'new':
                rec.amount = rec.variation_qty * rec.unit_rate
            elif rec.type == 'rate':
                old_rate = rec.boq_line_id.unit_rate if rec.boq_line_id else 0.0
                rec.amount = rec.original_qty * (rec.unit_rate - old_rate)
            else:
                rec.amount = 0.0

    @api.onchange('boq_line_id')
    def _onchange_boq_line_id(self):
        for rec in self:
            if rec.boq_line_id:
                rec.item_code = rec.boq_line_id.item_code
                rec.description = rec.boq_line_id.description
                rec.uom_id = rec.boq_line_id.uom_id
                rec.unit_rate = rec.boq_line_id.unit_rate

    @api.constrains('variation_qty')
    def _check_variation_qty(self):
        for rec in self:
            if rec.variation_qty < 0:
                raise ValidationError('Variation quantity cannot be negative.')

    def _prepare_new_boq_line_vals(self):
        self.ensure_one()
        return {
            'contract_id': self.contract_id.id,
            'sequence': (self.contract_id.boq_line_ids and max(self.contract_id.boq_line_ids.mapped('sequence') or [0]) + 10) or 10,
            'display_type': False,
            'item_code': self.item_code or self.variation_id.name,
            'description': self.description or 'New variation item',
            'uom_id': self.uom_id.id if self.uom_id else False,
            'contract_qty': self.variation_qty,
            'unit_rate': self.unit_rate,
        }
