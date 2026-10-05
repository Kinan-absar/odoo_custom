from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CashPlanReview(models.Model):
    _name = 'cash.plan.review'
    _description = 'Payment Planning Agent Review'
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default='New')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    review_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    state = fields.Selection([('draft', 'Review'), ('applied', 'Applied')], default='draft', readonly=True)
    line_ids = fields.One2many('cash.plan.review.line', 'review_id', string='Recommendations', copy=False)
    keep_count = fields.Integer(compute='_compute_summary')
    add_count = fields.Integer(compute='_compute_summary')
    update_count = fields.Integer(compute='_compute_summary')
    remove_count = fields.Integer(compute='_compute_summary')
    review_count = fields.Integer(compute='_compute_summary')

    @api.depends('line_ids.action')
    def _compute_summary(self):
        for rec in self:
            rec.keep_count = len(rec.line_ids.filtered(lambda l: l.action == 'keep'))
            rec.add_count = len(rec.line_ids.filtered(lambda l: l.action == 'add'))
            rec.update_count = len(rec.line_ids.filtered(lambda l: l.action in ('update', 'convert')))
            rec.remove_count = len(rec.line_ids.filtered(lambda l: l.action == 'remove'))
            rec.review_count = len(rec.line_ids.filtered(lambda l: l.action == 'review'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = _('Payment Review %s') % fields.Date.context_today(self)
        return super().create(vals_list)

    def action_apply_selected(self):
        self.ensure_one()
        selected = self.line_ids.filtered('apply')
        if not selected:
            raise UserError(_('Select at least one safe recommendation to apply.'))
        for item in selected:
            item._apply_recommendation()
        self.state = 'applied'
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class CashPlanReviewLine(models.Model):
    _name = 'cash.plan.review.line'
    _description = 'Payment Planning Agent Recommendation'
    _order = 'sequence, id'

    review_id = fields.Many2one('cash.plan.review', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    action = fields.Selection([
        ('keep', 'Keep'), ('add', 'Add'), ('update', 'Update'), ('convert', 'Convert to Payable'),
        ('remove', 'Remove'), ('review', 'Review'),
    ], required=True, readonly=True)
    severity = fields.Selection([('info', 'Info'), ('warning', 'Warning'), ('danger', 'Danger')], default='info', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    plan_line_id = fields.Many2one('cash.plan.line', string='Planned Payment', readonly=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    current_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    proposed_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one(related='review_id.currency_id', readonly=True)
    reason = fields.Text(readonly=True)
    apply = fields.Boolean(string='Apply', default=False)
    can_apply = fields.Boolean(default=False, readonly=True)
    applied = fields.Boolean(default=False, readonly=True)

    def _apply_recommendation(self):
        self.ensure_one()
        if self.applied or not self.can_apply:
            return
        line = self.plan_line_id
        if self.action == 'remove' and line and line.state == 'planned' and line.ceo_decision == 'not_sent':
            line.action_cancel()
        elif self.action == 'update' and line and self.proposed_amount > 0 and line.state == 'planned' and line.ceo_decision == 'not_sent':
            line.write({'forecast_amount': self.proposed_amount})
        else:
            raise UserError(_('This recommendation is review-only and cannot be applied automatically.'))
        self.applied = True


class CashPlanLinePaymentAgent(models.Model):
    _inherit = 'cash.plan.line'

    @api.model
    def action_run_payment_review_agent(self):
        company = self.env.company
        Review = self.env['cash.plan.review']
        ReviewLine = self.env['cash.plan.review.line']
        review = Review.create({'company_id': company.id})
        recommendations = []

        planned = self.search([
            ('company_id', '=', company.id), ('flow_type', '=', 'out'),
            ('transaction_type', '=', 'supplier'), ('state', '=', 'planned'),
        ])
        active_po_lines = planned.filtered(lambda l: l.purchase_order_ids)
        po_ids_already_planned = set(active_po_lines.mapped('purchase_order_ids').ids)

        for line in planned:
            pos = line.purchase_order_ids
            if not pos:
                recommendations.append(self._agent_vals(review, line, 'review',
                    _('Supplier-balance planned payment. Compare it with the current open payable balance before changing it.'),
                    severity='warning'))
                continue

            invalid = pos.filtered(lambda po: po.state not in ('purchase', 'done'))
            billed = pos.filtered(lambda po: getattr(po, 'invoice_status', False) in ('invoiced', 'fully_billed'))
            nothing_to_bill = pos.filtered(lambda po: getattr(po, 'invoice_status', False) == 'no')

            if invalid:
                recommendations.append(self._agent_vals(review, line, 'remove',
                    _('Linked PO is no longer a valid confirmed Purchase Order: %s.') % ', '.join(invalid.mapped('name')),
                    severity='danger', can_apply=self._safe_to_change(line)))
            elif billed:
                recommendations.append(self._agent_vals(review, line, 'convert',
                    _('PO has been billed. Stop treating this obligation as an uninvoiced PO and review it through supplier payables: %s.') % ', '.join(billed.mapped('name')),
                    severity='warning'))
            elif nothing_to_bill and len(nothing_to_bill) == len(pos):
                due = sum(max(po.amount_paid_residual, 0.0) for po in pos)
                if company.currency_id.compare_amounts(due, line.forecast_amount) == 0:
                    recommendations.append(self._agent_vals(review, line, 'keep',
                        _('PO is confirmed, still Nothing to Bill, and the planned amount matches the current PO due balance.')))
                elif due <= 0:
                    recommendations.append(self._agent_vals(review, line, 'review',
                        _('PO is still Nothing to Bill but its tracked due balance is zero. Check whether it has already been paid.'), severity='warning'))
                else:
                    recommendations.append(self._agent_vals(review, line, 'update',
                        _('PO is still Nothing to Bill, but the current PO due balance is %s instead of the planned %s.') %
                        (format(due, ',.2f'), format(line.forecast_amount, ',.2f')),
                        severity='warning', proposed=due, can_apply=self._safe_to_change(line)))
            else:
                recommendations.append(self._agent_vals(review, line, 'review',
                    _('The linked PO billing status is not a clean Nothing-to-Bill case. Review before changing the plan.'), severity='warning'))

        # Find confirmed, uninvoiced supplier POs that are not represented by an active planned payment.
        po_domain = [('company_id', '=', company.id), ('state', 'in', ('purchase', 'done')), ('invoice_status', '=', 'no')]
        for po in self.env['purchase.order'].search(po_domain):
            if po.id in po_ids_already_planned:
                continue
            due = max(po.amount_paid_residual, 0.0)
            if company.currency_id.is_zero(due):
                continue
            recommendations.append({
                'review_id': review.id, 'action': 'add', 'severity': 'info',
                'partner_id': po.partner_id.id, 'purchase_order_id': po.id,
                'current_amount': 0.0, 'proposed_amount': due,
                'reason': _('Confirmed PO is Nothing to Bill and has a remaining tracked balance, but no active PO-based planned payment currently links to it. Review before adding.'),
                'can_apply': False,
            })

        if recommendations:
            ReviewLine.create(recommendations)
        return {
            'type': 'ir.actions.act_window', 'name': _('Payment Review Agent'),
            'res_model': 'cash.plan.review', 'res_id': review.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _safe_to_change(self, line):
        return bool(line.state == 'planned' and getattr(line, 'ceo_decision', 'not_sent') == 'not_sent' and not line.is_locked)

    def _agent_vals(self, review, line, action, reason, severity='info', proposed=0.0, can_apply=False):
        return {
            'review_id': review.id, 'action': action, 'severity': severity,
            'partner_id': line.partner_id.id, 'plan_line_id': line.id,
            'purchase_order_id': line.purchase_order_ids[:1].id if line.purchase_order_ids else False,
            'current_amount': line.forecast_amount, 'proposed_amount': proposed or line.forecast_amount,
            'reason': reason, 'can_apply': can_apply,
        }
