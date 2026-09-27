from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class ConstructionContractOrder(models.Model):
    _name = 'construction.contract.order'
    _description = 'Construction Contract Order / Scope Package'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char(string='Contract Order', required=True, copy=False, default='New', tracking=True)
    contract_id = fields.Many2one('construction.contract', required=True, ondelete='cascade', tracking=True, index=True)
    sale_order_id = fields.Many2one('sale.order', string='Source Sales Order', required=True, ondelete='restrict', tracking=True, index=True)
    scope_name = fields.Char(string='Scope / Package', tracking=True)
    partner_id = fields.Many2one(related='contract_id.partner_id', store=True)
    project_id = fields.Many2one(related='contract_id.project_id', store=True)
    company_id = fields.Many2one(related='contract_id.company_id', store=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True)
    payment_term_id = fields.Many2one(related='sale_order_id.payment_term_id', string='Payment Terms', readonly=True)
    customer_reference = fields.Char(related='sale_order_id.client_order_ref', string='Customer Reference', readonly=True)
    order_amount = fields.Monetary(string='Order Amount', related='sale_order_id.amount_untaxed', currency_field='currency_id', store=True)
    boq_line_ids = fields.One2many('construction.contract.boq.line', 'contract_order_id', string='BOQ Lines')
    boq_amount = fields.Monetary(string='BOQ Amount', currency_field='currency_id', compute='_compute_boq_amount', store=True)
    measurement_ids = fields.One2many('construction.measurement', 'contract_order_id', string='Measurements')
    ipc_ids = fields.One2many('construction.ipc', 'contract_order_id', string='IPCs')
    measurement_count = fields.Integer(compute='_compute_counts')
    ipc_count = fields.Integer(compute='_compute_counts')
    state = fields.Selection(related='contract_id.state', string='Contract Status', readonly=True)

    _sql_constraints = [
        ('sale_order_unique_contract_order', 'unique(sale_order_id)', 'This Sales Order is already linked to a Contract Order.'),
    ]

    @api.depends('boq_line_ids.total_amount')
    def _compute_boq_amount(self):
        for rec in self:
            rec.boq_amount = sum(rec.boq_line_ids.filtered(lambda l: not l.display_type).mapped('total_amount'))

    def _compute_counts(self):
        for rec in self:
            rec.measurement_count = len(rec.measurement_ids)
            rec.ipc_count = len(rec.ipc_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('construction.contract.order') or 'New'
        records = super().create(vals_list)
        for rec in records:
            if rec.sale_order_id.partner_id.commercial_partner_id != rec.contract_id.partner_id.commercial_partner_id:
                raise ValidationError(_('The Sales Order customer must match the Client Contract customer.'))
            if rec.sale_order_id.construction_project_id and rec.contract_id.project_id and rec.sale_order_id.construction_project_id != rec.contract_id.project_id:
                raise ValidationError(_('The Sales Order project must match the Client Contract project.'))
        return records

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Sales Order'), 'res_model': 'sale.order',
            'view_mode': 'form', 'res_id': self.sale_order_id.id, 'target': 'current',
        }

    def action_view_measurements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Measurements'), 'res_model': 'construction.measurement',
            'view_mode': 'list,form', 'domain': [('contract_order_id', '=', self.id)],
            'context': {'default_contract_id': self.contract_id.id, 'default_contract_order_id': self.id},
        }

    def action_view_ipcs(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('IPCs'), 'res_model': 'construction.ipc',
            'view_mode': 'list,form', 'domain': [('contract_order_id', '=', self.id)],
            'context': {'default_contract_id': self.contract_id.id, 'default_contract_order_id': self.id},
        }

    def action_refresh_boq_from_sale(self):
        self.ensure_one()
        if self.measurement_ids or self.ipc_ids:
            raise UserError(_('The BOQ cannot be refreshed after Measurements or IPCs exist for this Contract Order.'))
        self.boq_line_ids.unlink()
        commands = self.sale_order_id._prepare_construction_boq_commands(contract_order_id=self.id)
        self.contract_id.write({'boq_line_ids': commands})
        self.message_post(body=_('BOQ refreshed from Sales Order %s.') % self.sale_order_id.name)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
