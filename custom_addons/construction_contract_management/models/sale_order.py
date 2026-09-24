from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    construction_project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True,
        domain="[('company_id', 'in', [False, company_id])]",
        help='Construction project that will be transferred to the Client Contract.',
    )

    construction_contract_ids = fields.One2many(
        'construction.contract',
        'sale_order_id',
        string='Construction Contracts',
        copy=False,
    )
    construction_contract_count = fields.Integer(
        string='Construction Contracts',
        compute='_compute_construction_contract_count',
    )

    @api.depends('construction_contract_ids')
    def _compute_construction_contract_count(self):
        for order in self:
            order.construction_contract_count = len(order.construction_contract_ids)

    def _prepare_construction_boq_commands(self):
        self.ensure_one()
        commands = []
        for line in self.order_line.sorted(key=lambda l: (l.sequence, l.id)):
            if line.display_type:
                commands.append((0, 0, {
                    'sequence': line.sequence,
                    'display_type': line.display_type,
                    'description': line.name or '',
                    'sale_order_line_id': line.id,
                }))
                continue

            qty = line.product_uom_qty or 0.0
            # Use subtotal/quantity so the BOQ reproduces Odoo's commercial
            # amount after discount (and line-level rounding) as closely as possible.
            effective_rate = 0.0
            if not float_is_zero(qty, precision_rounding=line.product_uom.rounding if line.product_uom else 0.000001):
                effective_rate = line.price_subtotal / qty

            commands.append((0, 0, {
                'sequence': line.sequence,
                'item_code': line.product_id.default_code or '',
                'description': line.name or line.product_id.display_name,
                'uom_id': line.product_uom.id if line.product_uom else False,
                'contract_qty': qty,
                'quoted_unit_rate': line.price_unit,
                'discount_percent': line.discount,
                'unit_rate': effective_rate,
                'sale_order_line_id': line.id,
            }))
        return commands

    def _prepare_construction_contract_vals(self):
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
            'boq_line_ids': self._prepare_construction_boq_commands(),
        }

        # Native project link owned by this module. This deliberately does not
        # depend on a Studio field, so quotation-to-contract conversion is stable
        # across databases and deployments.
        if self.construction_project_id:
            vals['project_id'] = self.construction_project_id.id
        return vals

    def action_create_construction_contract(self):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_('The quotation must be confirmed before creating a client contract.'))
        if self.construction_contract_ids:
            return self.action_view_construction_contract()

        contract = self.env['construction.contract'].create(self._prepare_construction_contract_vals())
        contract.message_post(body=_('Created from Sales Order %s.') % self.name)
        self.message_post(body=_('Client Contract %s was created from this Sales Order.') % contract.name)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Client Contract'),
            'res_model': 'construction.contract',
            'view_mode': 'form',
            'res_id': contract.id,
            'target': 'current',
        }

    def action_view_construction_contract(self):
        self.ensure_one()
        contracts = self.construction_contract_ids
        if not contracts:
            raise UserError(_('No construction contract is linked to this Sales Order.'))
        if len(contracts) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Client Contract'),
                'res_model': 'construction.contract',
                'view_mode': 'form',
                'res_id': contracts.id,
                'target': 'current',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Construction Contracts'),
            'res_model': 'construction.contract',
            'view_mode': 'list,form',
            'domain': [('id', 'in', contracts.ids)],
            'target': 'current',
        }
