from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    construction_project_id = fields.Many2one(
        'project.project', string='Project', tracking=True,
        domain="[('company_id', 'in', [False, company_id])]",
        help='Construction project used when creating/linking a Client Contract.',
    )
    construction_contract_order_id = fields.One2many(
        'construction.contract.order', 'sale_order_id', string='Contract Order', copy=False,
    )
    construction_contract_count = fields.Integer(compute='_compute_construction_contract_count')

    @api.depends('construction_contract_order_id')
    def _compute_construction_contract_count(self):
        for order in self:
            order.construction_contract_count = len(order.construction_contract_order_id)

    def _prepare_construction_boq_commands(self, contract_order_id=False):
        self.ensure_one()
        commands = []
        for line in self.order_line.sorted(key=lambda l: (l.sequence, l.id)):
            base = {
                'sequence': line.sequence,
                'description': line.name or '',
                'sale_order_line_id': line.id,
            }
            if contract_order_id:
                base['contract_order_id'] = contract_order_id
            if line.display_type:
                base['display_type'] = line.display_type
                commands.append((0, 0, base))
                continue
            qty = line.product_uom_qty or 0.0
            effective_rate = 0.0
            rounding = line.product_uom.rounding if line.product_uom else 0.000001
            if not float_is_zero(qty, precision_rounding=rounding):
                effective_rate = line.price_subtotal / qty
            base.update({
                'item_code': line.product_id.default_code or '',
                'description': line.name or line.product_id.display_name,
                'uom_id': line.product_uom.id if line.product_uom else False,
                'contract_qty': qty,
                'quoted_unit_rate': line.price_unit,
                'discount_percent': line.discount,
                'unit_rate': effective_rate,
            })
            commands.append((0, 0, base))
        return commands

    def _prepare_construction_contract_vals(self, include_boq=True):
        self.ensure_one()
        vals = {
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'contract_direction': 'inbound',
            'payment_term_id': self.payment_term_id.id if self.payment_term_id else False,
            'customer_reference': self.client_order_ref or '',
            'sale_order_id': self.id,
            'date_start': fields.Date.to_date(self.date_order) if self.date_order else fields.Date.context_today(self),
            'original_amount': self.amount_untaxed,
            'scope': self.note or '',
        }
        if include_boq:
            vals['boq_line_ids'] = self._prepare_construction_boq_commands()
        if self.construction_project_id:
            vals['project_id'] = self.construction_project_id.id
        return vals

    def action_create_construction_contract(self):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_('The quotation must be confirmed before creating/linking a client contract.'))
        if self.construction_contract_order_id:
            return self.action_view_construction_contract()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create / Link Client Contract'),
            'res_model': 'sale.construction.contract.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id, 'default_sale_order_id': self.id},
        }

    def action_view_construction_contract(self):
        self.ensure_one()
        package = self.construction_contract_order_id[:1]
        if not package:
            raise UserError(_('No Contract Order is linked to this Sales Order.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Contract Order'),
            'res_model': 'construction.contract.order', 'view_mode': 'form',
            'res_id': package.id, 'target': 'current',
        }
