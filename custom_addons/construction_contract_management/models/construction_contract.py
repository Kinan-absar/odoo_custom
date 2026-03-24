from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    revised_amount = fields.Monetary(
        string='Revised Amount',
        currency_field='currency_id',
        compute='_compute_revised_amount',
        store=True,
    )

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
    advance_ids = fields.One2many('construction.advance', 'contract_id', string='Advances')
    advance_count = fields.Integer(compute='_compute_advance_count')

    retention_held = fields.Monetary(
        string='Retention Held',
        currency_field='currency_id',
        compute='_compute_retention_balances',
        store=True,
    )
    retention_released = fields.Monetary(
        string='Retention Released',
        currency_field='currency_id',
        compute='_compute_retention_balances',
        store=True,
    )
    retention_balance = fields.Monetary(
        string='Retention Balance',
        currency_field='currency_id',
        compute='_compute_retention_balances',
        store=True,
    )

    retention_release_ids = fields.One2many(
        'construction.retention.release',
        'contract_id',
        string='Retention Releases',
    )
    retention_release_count = fields.Integer(compute='_compute_retention_release_count')

    total_measured_amount = fields.Monetary(
        string='Total Measured Amount',
        currency_field='currency_id',
        compute='_compute_summary_amounts',
        store=True,
    )

    total_certified_amount = fields.Monetary(
        string='Total Certified Amount',
        currency_field='currency_id',
        compute='_compute_summary_amounts',
        store=True,
    )

    total_move_amount = fields.Monetary(
        string='Total Invoiced/Billed',
        currency_field='currency_id',
        compute='_compute_summary_amounts',
        store=True,
    )

    total_paid_amount = fields.Monetary(
        string='Total Paid',
        currency_field='currency_id',
        compute='_compute_summary_amounts',
        store=True,
    )

    completion_percent = fields.Float(
        string='Completion %',
        compute='_compute_summary_amounts',
        store=True,
    )
    # Accounting setup
    journal_id = fields.Many2one('account.journal', string='Accounting Journal')
    work_account_id = fields.Many2one('account.account', string='Work Account')
    advance_account_id = fields.Many2one('account.account', string='Advance Recovery Account')
    retention_account_id = fields.Many2one('account.account', string='Retention Account')
    tax_id = fields.Many2one('account.tax', string='VAT Tax')

    notes = fields.Text(string='Internal Notes')

    portal_visibility_restricted = fields.Boolean(
        string='Restrict Portal Visibility',
        help='When enabled, only the selected portal employees can see this contract and related records in the portal.',
    )
    portal_employee_ids = fields.Many2many(
        'hr.employee',
        'construction_contract_portal_employee_rel',
        'contract_id',
        'employee_id',
        string='Portal Employees',
        help='Employees allowed to see this contract and related records in the portal.',
    )
    internal_visibility_restricted = fields.Boolean(
        string='Restrict Internal Visibility',
        help='When enabled, only the selected internal employees can see this contract and related records in Odoo.',
    )
    internal_employee_ids = fields.Many2many(
        'hr.employee',
        'construction_contract_internal_employee_rel',
        'contract_id',
        'employee_id',
        string='Internal Employees',
        help='Employees allowed to see this contract and related records inside Odoo.',
    )

    boq_line_ids = fields.One2many('construction.contract.boq.line', 'contract_id', string='BOQ Lines')
    measurement_ids = fields.One2many('construction.measurement', 'contract_id', string='Measurements')
    ipc_ids = fields.One2many('construction.ipc', 'contract_id', string='IPCs')

    boq_line_count = fields.Integer(compute='_compute_counts')
    measurement_count = fields.Integer(compute='_compute_counts')
    ipc_count = fields.Integer(compute='_compute_counts')
    variation_count = fields.Integer(compute='_compute_variation_count')

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
            rec.revised_amount = sum(rec.boq_line_ids.mapped('revised_amount')) if rec.boq_line_ids else rec.original_amount

    @api.depends('original_amount', 'advance_percent')
    def _compute_advance_amount(self):
        for rec in self:
            rec.advance_amount = (rec.original_amount or 0.0) * ((rec.advance_percent or 0.0) / 100.0)

    @api.depends('advance_amount', 'advance_recovered')
    def _compute_advance_balance(self):
        for rec in self:
            rec.advance_balance = (rec.advance_amount or 0.0) - (rec.advance_recovered or 0.0)

    def _compute_counts(self):
        for rec in self:
            rec.boq_line_count = len(rec.boq_line_ids)
            rec.measurement_count = len(rec.measurement_ids)
            rec.ipc_count = len(rec.ipc_ids)

    def _compute_variation_count(self):
        for rec in self:
            rec.variation_count = self.env['construction.variation'].search_count([
                ('contract_id', '=', rec.id)
            ])

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('construction.contract') or 'New'
        return super().create(vals)

    def _get_report_base_filename(self):
        self.ensure_one()
        return f"Contract_{self.name}"

    def action_submit_review(self):
        self.state = 'under_review'

    def action_approve(self):
        self.state = 'approved'

    def action_activate(self):
        self.state = 'active'

    def action_complete(self):
        self.state = 'completed'

    def action_close(self):
        self.state = 'closed'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        self.state = 'draft'
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
    def action_view_variations(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Variations',
            'res_model': 'construction.variation',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
    def _compute_advance_count(self):
        for rec in self:
            rec.advance_count = self.env['construction.advance'].search_count([
                ('contract_id', '=', rec.id)
            ])
    def action_view_advances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Advances',
            'res_model': 'construction.advance',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
    
    @api.depends(
        'ipc_ids.retention_amount',
        'ipc_ids.state',
        'retention_release_ids.amount',
        'retention_release_ids.state',
    )
    def _compute_retention_balances(self):
        for rec in self:
            held = sum(
                rec.ipc_ids.filtered(lambda x: x.state in ['approved', 'done']).mapped('retention_amount')
            )
            released = sum(
                rec.retention_release_ids.filtered(lambda x: x.state in ['posted']).mapped('amount')
            )
            rec.retention_held = held
            rec.retention_released = released
            rec.retention_balance = held - released


    def _compute_retention_release_count(self):
        for rec in self:
            rec.retention_release_count = self.env['construction.retention.release'].search_count([
                ('contract_id', '=', rec.id)
            ])


    def action_view_retention_releases(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Retention Releases',
            'res_model': 'construction.retention.release',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
            'context': {'default_contract_id': self.id},
        }
    
    @api.depends(
        'boq_line_ids.measured_qty',
        'boq_line_ids.certified_qty',
        'boq_line_ids.unit_rate',
        'boq_line_ids.revised_unit_rate',
        'ipc_ids.current_work_value',
        'ipc_ids.move_id',
        'ipc_ids.move_id.amount_total',
        'ipc_ids.move_id.payment_state',
        'ipc_ids.move_id.amount_residual',
        'revised_amount',
    )
    def _compute_summary_amounts(self):
        for rec in self:
            total_measured = 0.0
            total_certified = 0.0

            for line in rec.boq_line_ids:
                rate = line.revised_unit_rate or line.unit_rate
                total_measured += (line.measured_qty or 0.0) * rate
                total_certified += (line.certified_qty or 0.0) * rate

            moves = rec.ipc_ids.mapped('move_id').filtered(lambda m: m.state != 'cancel')
            total_move = sum(moves.mapped('amount_total'))
            total_paid = sum((m.amount_total - m.amount_residual) for m in moves)

            completion = 0.0
            if rec.revised_amount:
                completion = (total_certified / rec.revised_amount) * 100.0

            rec.total_measured_amount = total_measured
            rec.total_certified_amount = total_certified
            rec.total_move_amount = total_move
            rec.total_paid_amount = total_paid
            rec.completion_percent = completion
