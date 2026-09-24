from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleConstructionContractWizard(models.TransientModel):
    _name = 'sale.construction.contract.wizard'
    _description = 'Create or Link Client Contract'

    sale_order_id = fields.Many2one('sale.order', required=True, readonly=True)
    partner_id = fields.Many2one(related='sale_order_id.partner_id', readonly=True)
    project_id = fields.Many2one(related='sale_order_id.construction_project_id', readonly=True)
    mode = fields.Selection([
        ('new', 'Create New Client Contract'),
        ('existing', 'Add as Contract Order to Existing Contract'),
    ], required=True, default='existing')
    contract_id = fields.Many2one('construction.contract', string='Existing Client Contract')
    scope_name = fields.Char(string='Scope / Package Name', required=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        order = self.env['sale.order'].browse(self.env.context.get('active_id'))
        if order:
            vals.update({
                'sale_order_id': order.id,
                'scope_name': order.client_order_ref or order.name,
            })
            domain = [('partner_id.commercial_partner_id', '=', order.partner_id.commercial_partner_id.id), ('contract_direction', '=', 'inbound')]
            if order.construction_project_id:
                domain.append(('project_id', '=', order.construction_project_id.id))
            existing = self.env['construction.contract'].search(domain, limit=1)
            vals['mode'] = 'existing' if existing else 'new'
            vals['contract_id'] = existing.id if existing else False
        return vals

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_order_id
        if order.state != 'sale':
            raise UserError(_('The quotation must be confirmed first.'))
        if order.construction_contract_order_id:
            return order.action_view_construction_contract()

        if self.mode == 'new':
            contract_vals = order._prepare_construction_contract_vals(include_boq=False)
            contract = self.env['construction.contract'].create(contract_vals)
        else:
            contract = self.contract_id
            if not contract:
                raise UserError(_('Select an existing Client Contract.'))
            if contract.partner_id.commercial_partner_id != order.partner_id.commercial_partner_id:
                raise UserError(_('The contract customer does not match the Sales Order customer.'))
            if order.construction_project_id and contract.project_id != order.construction_project_id:
                raise UserError(_('The contract project does not match the Sales Order project.'))

        contract_order = self.env['construction.contract.order'].create({
            'contract_id': contract.id,
            'sale_order_id': order.id,
            'scope_name': self.scope_name or order.name,
        })
        contract.write({'boq_line_ids': order._prepare_construction_boq_commands(contract_order_id=contract_order.id)})
        if not contract.sale_order_id:
            contract.sale_order_id = order.id
        # Master contract amount represents all independent awarded Sales Orders.
        contract.original_amount = sum(contract.contract_order_ids.mapped('order_amount'))
        contract.message_post(body=_('Sales Order %s added as Contract Order %s.') % (order.name, contract_order.name))
        order.message_post(body=_('Linked to Client Contract %s as %s.') % (contract.name, contract_order.name))
        return {
            'type': 'ir.actions.act_window', 'name': _('Contract Order'),
            'res_model': 'construction.contract.order', 'view_mode': 'form',
            'res_id': contract_order.id, 'target': 'current',
        }
