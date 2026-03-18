from odoo import api, fields, models


class ConstructionContract(models.Model):
    _name = 'construction.contract'
    _description = 'Construction Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Contract Reference', required=True, copy=False, default='New', tracking=True)
    project_id = fields.Many2one('project.project', string='Project', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Partner', required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id', store=True)

    contract_direction = fields.Selection([
        ('inbound', 'Inbound Contract'),
        ('outbound', 'Outbound Contract'),
    ], string='Contract Direction', required=True, default='outbound', tracking=True)

    scope = fields.Text(string='Scope of Work')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')

    original_amount = fields.Monetary(string='Original Amount', currency_field='currency_id', tracking=True)
    revised_amount = fields.Monetary(string='Revised Amount', currency_field='currency_id', compute='_compute_revised_amount', store=True)
    retention_percent = fields.Float(string='Retention %')
    advance_percent = fields.Float(string='Advance %')
    vat_percent = fields.Float(string='VAT %', default=15.0)

    advance_amount = fields.Monetary(
        string='Advance Amount',
        currency_field='currency_id',
        compute='_compute_advance_amount',
        store=True,
    )

    advance_recovered = fields.Monetary(
        string='Advance Recovered',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
    )

    advance_balance = fields.Monetary(
        string='Advance Balance',
        currency_field='currency_id',
        compute='_compute_advance_balance',
        store=True,
    )

    @api.depends('original_amount', 'advance_percent')
    def _compute_advance_amount(self):
        for rec in self:
            rec.advance_amount = (rec.original_amount or 0.0) * ((rec.advance_percent or 0.0) / 100.0)

    @api.depends('advance_amount', 'advance_recovered')
    def _compute_advance_balance(self):
        for rec in self:
            rec.advance_balance = (rec.advance_amount or 0.0) - (rec.advance_recovered or 0.0)
    notes = fields.Text(string='Internal Notes')

    boq_line_ids = fields.One2many('construction.contract.boq.line', 'contract_id', string='BOQ Lines')
    measurement_ids = fields.One2many('construction.measurement', 'contract_id', string='Measurements')
    ipc_ids = fields.One2many('construction.ipc', 'contract_id', string='IPCs')

    boq_line_count = fields.Integer(compute='_compute_counts')
    measurement_count = fields.Integer(compute='_compute_counts')
    ipc_count = fields.Integer(compute='_compute_counts')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)

    @api.depends('boq_line_ids.revised_amount')
    def _compute_revised_amount(self):
        for rec in self:
            if rec.boq_line_ids:
                rec.revised_amount = sum(rec.boq_line_ids.mapped('revised_amount'))
            else:
                rec.revised_amount = rec.original_amount

    def _compute_counts(self):
        for rec in self:
            rec.boq_line_count = len(rec.boq_line_ids)
            rec.measurement_count = len(rec.measurement_ids)
            rec.ipc_count = len(rec.ipc_ids)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.contract') or 'New'
        return super().create(vals)

    def action_submit_review(self):
        for rec in self:
            rec.state = 'under_review'

    def action_approve(self):
        for rec in self:
            rec.state = 'approved'

    def action_activate(self):
        for rec in self:
            rec.state = 'active'

    def action_complete(self):
        for rec in self:
            rec.state = 'completed'

    def action_close(self):
        for rec in self:
            rec.state = 'closed'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            rec.state = 'draft'
    def action_view_measurements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Measurements',
            'res_model': 'construction.measurement',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }

    def action_view_ipcs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'IPCs',
            'res_model': 'construction.ipc',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
    variation_count = fields.Integer(compute='_compute_variation_count')

    def _compute_variation_count(self):
        for rec in self:
            rec.variation_count = self.env['construction.variation'].search_count([
                ('contract_id', '=', rec.id)
            ])


    def action_view_variations(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Variations',
            'res_model': 'construction.variation',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }