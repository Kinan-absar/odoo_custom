from collections import defaultdict
from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CashPlanReview(models.Model):
    _name = 'cash.plan.review'
    _description = 'Payment Planning Agent Review'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default='New')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    review_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    year = fields.Selection(
        selection=lambda self: [('all', _('All Open'))] + [(str(y), str(y)) for y in range(date.today().year + 1, date.today().year - 7, -1)],
        string='Year', default=lambda self: str(date.today().year), required=True,
        help='Filters planned-payment dates and purchase-order dates. Supplier aging remains the full live open balance so older unpaid items are not accidentally ignored.',
    )
    state = fields.Selection([
        ('draft', 'Review'),
        ('partial', 'Partially Applied'),
        ('applied', 'Safe Changes Applied'),
    ], default='draft', readonly=True, tracking=True)
    line_ids = fields.One2many('cash.plan.review.line', 'review_id', string='Recommendations', copy=False)

    keep_count = fields.Integer(compute='_compute_summary')
    add_count = fields.Integer(compute='_compute_summary')
    update_count = fields.Integer(compute='_compute_summary')
    remove_count = fields.Integer(compute='_compute_summary')
    review_count = fields.Integer(compute='_compute_summary')
    safe_count = fields.Integer(compute='_compute_summary', string='Safe Changes')
    selected_count = fields.Integer(compute='_compute_summary', string='Selected')

    @api.depends('line_ids.action', 'line_ids.can_apply', 'line_ids.apply', 'line_ids.applied')
    def _compute_summary(self):
        for rec in self:
            rec.keep_count = len(rec.line_ids.filtered(lambda l: l.action == 'keep'))
            rec.add_count = len(rec.line_ids.filtered(lambda l: l.action == 'add'))
            rec.update_count = len(rec.line_ids.filtered(lambda l: l.action in ('update', 'convert')))
            rec.remove_count = len(rec.line_ids.filtered(lambda l: l.action == 'remove'))
            rec.review_count = len(rec.line_ids.filtered(lambda l: l.action == 'review'))
            rec.safe_count = len(rec.line_ids.filtered(lambda l: l.can_apply and not l.applied))
            rec.selected_count = len(rec.line_ids.filtered(lambda l: l.can_apply and l.apply and not l.applied))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = _('Payment Review %s') % fields.Date.context_today(self)
        return super().create(vals_list)

    @api.model
    def action_run_payment_review_agent(self):
        return self.env['cash.plan.line'].action_run_payment_review_agent()

    def action_refresh_review(self):
        self.ensure_one()
        if self.line_ids.filtered('applied'):
            raise UserError(_('This review already has applied changes. Run a new Payment Review instead of refreshing it.'))
        self.line_ids.unlink()
        self.review_date = fields.Datetime.now()
        self.env['cash.plan.line']._populate_payment_review(self)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


    def action_open_recommendations(self):
        self.ensure_one()
        action = self.env.ref('internal_transfer_voucher.action_cash_plan_review_line').read()[0]
        action['domain'] = [('review_id', '=', self.id)]
        action['context'] = {
            'default_review_id': self.id,
            'search_default_not_applied': 1,
        }
        action['name'] = _('Recommendations - %s') % self.name
        return action

    def action_select_all_safe(self):
        self.ensure_one()
        safe = self.line_ids.filtered(lambda l: l.can_apply and not l.applied)
        (self.line_ids - safe).write({'apply': False})
        safe.write({'apply': True})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_clear_selection(self):
        self.ensure_one()
        self.line_ids.filtered('apply').write({'apply': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_apply_selected(self):
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.apply and l.can_apply and not l.applied)
        if not selected:
            raise UserError(_('Select at least one safe recommendation to apply.'))
        for item in selected:
            item._apply_recommendation()
        selected.write({'apply': False})
        remaining_safe = self.line_ids.filtered(lambda l: l.can_apply and not l.applied)
        self.state = 'partial' if remaining_safe else 'applied'
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class CashPlanReviewLine(models.Model):
    _name = 'cash.plan.review.line'
    _description = 'Payment Planning Agent Recommendation'
    _order = 'sequence, id'

    review_id = fields.Many2one('cash.plan.review', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    agent_action = fields.Selection([
        ('keep', 'Keep'),
        ('add', 'Add'),
        ('update', 'Update'),
        ('convert', 'Convert to Payable'),
        ('remove', 'Remove'),
        ('review', 'Review'),
    ], string='Agent Decision', readonly=True)
    action = fields.Selection([
        ('keep', 'Keep'),
        ('add', 'Add'),
        ('update', 'Update'),
        ('convert', 'Convert to Payable'),
        ('remove', 'Remove'),
        ('review', 'Review'),
    ], string='Decision', required=True)
    source_type = fields.Selection([
        ('existing_po', 'Existing PO Plan'),
        ('existing_payable', 'Existing Payable Plan'),
        ('existing_retention', 'Existing Retention Plan'),
        ('new_po', 'New PO Candidate'),
        ('new_payable', 'New Payable Candidate'),
        ('new_retention', 'New Retention Candidate'),
    ], readonly=True)
    severity = fields.Selection([
        ('info', 'Info'), ('warning', 'Warning'), ('danger', 'Danger')
    ], default='info', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    plan_line_id = fields.Many2one('cash.plan.line', string='Planned Payment', readonly=True)
    target_plan_line_id = fields.Many2one('cash.plan.line', string='Target Payable Plan', readonly=True)
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    bill_ids = fields.Many2many(
        'account.move', 'cash_plan_review_line_bill_rel', 'review_line_id', 'move_id',
        string='Open Bills', readonly=True,
    )
    current_amount = fields.Monetary(currency_field='currency_id', readonly=True)
    proposed_amount = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='review_id.currency_id', readonly=True)
    oldest_due_date = fields.Date(readonly=True)
    aging_summary = fields.Char(readonly=True)
    reason = fields.Text(readonly=True)
    apply = fields.Boolean(string='Apply', default=False)
    can_apply = fields.Boolean(default=False, readonly=True)
    applied = fields.Boolean(default=False, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('action') and not vals.get('agent_action'):
                vals['agent_action'] = vals['action']
        return super().create(vals_list)

    @api.onchange('action', 'proposed_amount')
    def _onchange_manual_decision(self):
        for rec in self:
            rec.can_apply = rec._decision_is_safely_applicable()
            if not rec.can_apply:
                rec.apply = False

    def write(self, vals):
        res = super().write(vals)
        if {'action', 'proposed_amount'} & set(vals) and not self.env.context.get('skip_recompute_can_apply'):
            for rec in self:
                safe = rec._decision_is_safely_applicable()
                updates = {}
                if rec.can_apply != safe:
                    updates['can_apply'] = safe
                if not safe and rec.apply:
                    updates['apply'] = False
                if updates:
                    super(CashPlanReviewLine, rec.with_context(skip_recompute_can_apply=True)).write(updates)
        return res

    def _decision_is_safely_applicable(self):
        self.ensure_one()
        if self.applied or self.action in ('keep', 'review'):
            return False
        if self.action == 'add':
            if self.source_type == 'new_payable':
                return self.proposed_amount > 0 and bool(self.partner_id)
            if self.source_type == 'new_po':
                po = self.purchase_order_id
                return bool(po and self.proposed_amount > 0 and po.state in ('purchase', 'done') and getattr(po, 'invoice_status', False) == 'no')
            if self.source_type == 'new_retention':
                return bool(self.purchase_order_id and self.partner_id and self.proposed_amount > 0)
            return False
        if self.action in ('update', 'remove'):
            return bool(self.plan_line_id and self._safe_line(self.plan_line_id) and (self.action != 'update' or self.proposed_amount > 0))
        if self.action == 'convert':
            if not self.plan_line_id or not self._safe_line(self.plan_line_id) or self.proposed_amount <= 0:
                return False
            return not self.target_plan_line_id or self._safe_line(self.target_plan_line_id)
        return False

    def action_toggle_apply(self):
        self.ensure_one()
        if not self.can_apply or self.applied:
            raise UserError(_('This recommendation is not currently safe to apply automatically. Change the decision/amount or review it manually.'))
        self.apply = not self.apply
        return {'type': 'ir.actions.client', 'tag': 'reload'}


    def action_apply_selected_from_list(self):
        if not self:
            raise UserError(_('Select at least one recommendation first.'))
        unsafe = self.filtered(lambda l: l.applied or not l._decision_is_safely_applicable())
        if unsafe:
            labels = []
            for line in unsafe[:8]:
                labels.append('%s - %s' % (line.partner_id.display_name or _('No Supplier'), dict(line._fields['action'].selection).get(line.action, line.action)))
            more = len(unsafe) - len(labels)
            msg = _('Some selected rows are not safe to apply yet:\n- %s') % '\n- '.join(labels)
            if more > 0:
                msg += _('\n...and %s more.') % more
            msg += _('\n\nChange the Decision / Proposed Amount first, or remove those rows from the selection.')
            raise UserError(msg)
        reviews = self.mapped('review_id')
        for line in self:
            line._apply_recommendation()
        for review in reviews:
            remaining_safe = review.line_ids.filtered(lambda l: l.can_apply and not l.applied)
            review.state = 'partial' if remaining_safe else 'applied'
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _apply_recommendation(self):
        self.ensure_one()
        if self.applied or not self.can_apply:
            return

        line = self.plan_line_id
        company = self.review_id.company_id

        if self.action == 'remove':
            if not line or not self._safe_line(line):
                raise UserError(_('This planned payment is no longer safe to remove automatically. Run a new review.'))
            self._prepare_line_for_agent_change(line)
            line.action_cancel()

        elif self.action == 'update':
            if not line or not self._safe_line(line) or self.proposed_amount <= 0:
                raise UserError(_('This planned payment is no longer safe to update automatically. Run a new review.'))
            self._prepare_line_for_agent_change(line)
            vals = {'forecast_amount': self.proposed_amount}
            if self.source_type == 'existing_payable':
                vals.update({
                    'bill_ids': [(6, 0, self.bill_ids.ids)],
                })
            line.with_context(allow_locked_write=True).write(vals)

        elif self.action == 'convert':
            if not line or not self._safe_line(line):
                raise UserError(_('This PO planned payment is no longer safe to convert automatically. Run a new review.'))
            self._prepare_line_for_agent_change(line)
            target = self.target_plan_line_id
            if target:
                if not self._safe_line(target):
                    raise UserError(_('The target supplier-balance planned payment is locked. Run a new review.'))
                self._prepare_line_for_agent_change(target)
                target.with_context(allow_locked_write=True).write({
                    'forecast_amount': self.proposed_amount,
                    'bill_ids': [(6, 0, self.bill_ids.ids)],
                })
                line.action_cancel()
            else:
                if self.proposed_amount <= 0:
                    raise UserError(_('There is no positive supplier payable balance to convert this PO into.'))
                # Once this obligation is treated through supplier aging, the PO
                # link must be removed. A PO link means this is a PO-based payment.
                line.with_context(allow_locked_write=True).write({
                    'name': _('Balance Due - %s') % self.partner_id.display_name,
                    'bill_ids': [(6, 0, self.bill_ids.ids)],
                    'forecast_amount': self.proposed_amount,
                })

        elif self.action == 'add' and self.source_type == 'new_po':
            po = self.purchase_order_id
            if not po or po.state not in ('purchase', 'done') or getattr(po, 'invoice_status', False) != 'no':
                raise UserError(_('The purchase order is no longer an eligible Nothing-to-Bill PO. Run a new review.'))
            if self.proposed_amount <= 0:
                raise UserError(_('Enter the amount you want to plan for this PO.'))
            existing = self.env['cash.plan.line'].search([
                ('company_id', '=', company.id),
                ('flow_type', '=', 'out'),
                ('transaction_type', '=', 'supplier'),
                ('state', 'not in', ('executed', 'cancel')),
                ('purchase_order_ids', 'in', po.id),
            ], limit=1)
            if existing:
                raise UserError(_('This PO is already represented by an active planned payment. Run a new review.'))
            category = self._suggest_category(po.partner_id.commercial_partner_id)
            self.env['cash.plan.line'].create({
                'name': _('%s - %s') % (po.name, po.partner_id.display_name),
                'company_id': company.id,
                'flow_type': 'out',
                'transaction_type': 'supplier',
                'category_id': category.id,
                'partner_id': po.partner_id.commercial_partner_id.id,
                'purchase_order_ids': [(6, 0, po.ids)],
                'forecast_amount': self.proposed_amount,
                'description': _('Created from Payment Review. User-confirmed PO amount.'),
            })

        elif self.action == 'add' and self.source_type == 'new_retention':
            po = self.purchase_order_id
            if not po or self.proposed_amount <= 0:
                raise UserError(_('The retention candidate is no longer valid. Run a new review.'))
            existing = self.env['cash.plan.line'].search([
                ('company_id', '=', company.id),
                ('flow_type', '=', 'out'),
                ('transaction_type', '=', 'supplier'),
                ('state', 'not in', ('executed', 'cancel')),
                ('purchase_order_ids', 'in', po.id),
            ]).filtered(lambda l: self.env['cash.plan.line']._agent_plan_basis(l) == 'retention')[:1]
            if existing:
                raise UserError(_('A retention planned payment already exists for %s. Run a new review.') % po.name)
            category = self._suggest_category(po.partner_id.commercial_partner_id)
            retention_account = self.env['account.account'].search([
                ('company_ids', 'in', company.id),
                ('code', '=', '201019'),
            ], limit=1)
            self.env['cash.plan.line'].create({
                'name': _('Retention - %s') % po.name,
                'company_id': company.id,
                'flow_type': 'out',
                'transaction_type': 'supplier',
                'category_id': category.id,
                'partner_id': po.partner_id.commercial_partner_id.id,
                'purchase_order_ids': [(6, 0, po.ids)],
                'bill_ids': [(6, 0, self.bill_ids.ids)],
                'account_id': retention_account.id if retention_account else False,
                'forecast_amount': self.proposed_amount,
                'description': _('Retention candidate created from Payment Review after PO amount vs gross posted invoices and Retention Payable cross-check.'),
            })

        elif self.action == 'add' and self.source_type == 'new_payable':
            if self.proposed_amount <= 0:
                raise UserError(_('There is no positive payable balance to add.'))
            # Re-check for an active supplier-balance line to avoid creating a duplicate
            candidates = self.env['cash.plan.line'].search([
                ('company_id', '=', company.id),
                ('flow_type', '=', 'out'),
                ('transaction_type', '=', 'supplier'),
                ('partner_id', '=', self.partner_id.id),
                ('state', 'not in', ('executed', 'cancel')),
            ])
            existing = candidates.filtered(lambda l: self.env['cash.plan.line']._agent_plan_basis(l) == 'payable')[:1]
            if existing:
                raise UserError(_('A supplier-balance planned payment now exists for %s. Run a new review.') % self.partner_id.display_name)

            category = self._suggest_category(self.partner_id)
            self.env['cash.plan.line'].create({
                'name': _('Balance Due - %s') % self.partner_id.display_name,
                'company_id': company.id,
                'flow_type': 'out',
                'transaction_type': 'supplier',
                'category_id': category.id,
                'partner_id': self.partner_id.id,
                'forecast_amount': self.proposed_amount,
                'bill_ids': [(6, 0, self.bill_ids.ids)],
                'description': _('Created from Payment Review Agent. %s') % (self.aging_summary or ''),
            })

        else:
            raise UserError(_('This recommendation is review-only and cannot be applied automatically.'))

        self.applied = True

    def _safe_line(self, line):
        """Lines the review may maintain without touching an executed/approved payment.

        Pending / held / rejected CEO items are still editable planning items. If the agent
        changes one of them we reset the approval to Not Sent so the revised amount/content
        must be reviewed again. Approved/adjusted and executed items are deliberately locked.
        """
        decision = getattr(line, 'ceo_decision', 'not_sent')
        return bool(
            line
            and line.state == 'planned'
            and decision in ('not_sent', 'pending', 'held', 'rejected', False)
            and not line.is_unplanned
        )

    def _prepare_line_for_agent_change(self, line):
        """Invalidate any pending CEO review before changing the planning item."""
        if not line or not self._safe_line(line):
            return
        decision = getattr(line, 'ceo_decision', 'not_sent')
        if decision in ('pending', 'held', 'rejected'):
            line.with_context(allow_locked_write=True).write({
                'ceo_decision': 'not_sent',
                'approved_amount': 0.0,
                'ceo_comment': False,
                'ceo_approved_by': False,
                'ceo_approved_date': False,
            })

    def _suggest_category(self, partner):
        existing = self.env['cash.plan.line'].search([
            ('company_id', '=', self.review_id.company_id.id),
            ('flow_type', '=', 'out'),
            ('transaction_type', '=', 'supplier'),
            ('partner_id', '=', partner.id),
            ('category_id', '!=', False),
        ], order='id desc', limit=1)
        if existing.category_id:
            return existing.category_id
        category = self.env.ref('internal_transfer_voucher.cat_out_supplier', raise_if_not_found=False)
        if not category:
            category = self.env['cash.plan.category'].search([
                ('flow_type', '=', 'out'),
                '|', ('company_id', '=', False), ('company_id', '=', self.review_id.company_id.id),
            ], limit=1)
        if not category:
            raise UserError(_('No outgoing cash-planning category is available.'))
        return category


class CashPlanLinePaymentAgent(models.Model):
    _inherit = 'cash.plan.line'

    @api.model
    def action_run_payment_review_agent(self):
        company = self.env.company
        review = self.env['cash.plan.review'].create({'company_id': company.id})
        self._populate_payment_review(review)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Review Agent'),
            'res_model': 'cash.plan.review',
            'res_id': review.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _populate_payment_review(self, review):
        company = review.company_id
        ReviewLine = self.env['cash.plan.review.line']
        recommendations = []

        planned_domain = [
            ('company_id', '=', company.id),
            ('flow_type', '=', 'out'),
            ('state', 'not in', ('executed', 'cancel')),
        ]
        if review.year != 'all':
            year = int(review.year)
            planned_domain += [('planned_date', '>=', date(year, 1, 1)), ('planned_date', '<=', date(year, 12, 31))]
        planned = self.search(planned_domain)
        supplier_lines = planned.filtered(lambda l: l.transaction_type == 'supplier')

        # Classification rule: retention is handled separately; otherwise a linked
        # PO means the planned payment is PO-based. If there is no PO link, it is a
        # supplier-balance/account payment.
        po_plan_lines = supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'po')
        balance_plan_lines = supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'payable')
        retention_plan_lines = supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'retention')

        payable_data = self._agent_get_payable_data(company)
        retention_data = self._agent_get_retention_data(company)

        # Choose one supplier-balance line per partner. Extra lines are duplicates.
        balance_by_partner = defaultdict(lambda: self.env['cash.plan.line'])
        for line in balance_plan_lines:
            balance_by_partner[line.partner_id.commercial_partner_id.id] |= line

        primary_balance = {}
        for partner_id, lines in balance_by_partner.items():
            # Prefer a draft/not-sent line because it can be maintained automatically.
            ordered = lines.sorted(key=lambda l: (0 if self._agent_safe_to_change(l) else 1, l.id))
            primary = ordered[:1]
            if primary:
                primary_balance[partner_id] = primary
            for duplicate in ordered[1:]:
                recommendations.append(self._agent_vals(
                    review, duplicate, 'remove',
                    _('Duplicate supplier-balance planned payment. Keep one balance line per supplier to avoid double planning.'),
                    severity='danger',
                    source_type='existing_payable',
                    can_apply=self._agent_safe_to_change(duplicate),
                ))

        # Review existing supplier-balance planned payments against live open payables.
        for partner_id, line in primary_balance.items():
            data = payable_data.get(partner_id, self._agent_empty_payable_data())
            due = data['net_due']
            if company.currency_id.is_zero(due) or due < 0:
                recommendations.append(self._agent_vals(
                    review, line, 'remove',
                    _('The supplier currently has no positive non-retention payable balance. The balance-based planned payment is no longer required.'),
                    severity='warning', source_type='existing_payable',
                    bills=data['bills'], oldest_due=data['oldest_due'], aging=data['aging_summary'],
                    can_apply=self._agent_safe_to_change(line), proposed=0.0,
                ))
            elif company.currency_id.compare_amounts(due, line.forecast_amount) != 0:
                recommendations.append(self._agent_vals(
                    review, line, 'update',
                    _('Update this supplier-balance plan to the current non-retention payable balance. %s') % data['aging_summary'],
                    severity='warning', source_type='existing_payable',
                    bills=data['bills'], oldest_due=data['oldest_due'], aging=data['aging_summary'],
                    proposed=due, can_apply=self._agent_safe_to_change(line),
                ))
            else:
                recommendations.append(self._agent_vals(
                    review, line, 'keep',
                    _('Supplier-balance planned payment matches the current non-retention payable balance. %s') % data['aging_summary'],
                    source_type='existing_payable', bills=data['bills'],
                    oldest_due=data['oldest_due'], aging=data['aging_summary'], proposed=due,
                ))

        # Retention engine: determine whether retention is ready to be planned from
        # PO amount vs gross posted invoiced work, then cross-check the Retention
        # Payable GL. Odoo's PO billing status is intentionally NOT used here.
        #
        # A PO is a retention candidate only when cumulative gross posted invoice
        # value sourced from its PO lines reaches the PO untaxed amount and its
        # related bills generated retention in the Retention Payable account.
        # Supplier-level open retention is then used as a control total. Where a
        # supplier has several completed POs and the open GL balance is lower than
        # the sum of generated retention, allocation is ambiguous and stays Review.
        retention_pos = self.env['purchase.order']
        for line in retention_plan_lines:
            retention_pos |= line.purchase_order_ids
        # Also discover completed-retention candidates that are not already planned.
        po_scan_domain = [('company_id', '=', company.id), ('state', 'in', ('purchase', 'done'))]
        if review.year != 'all':
            year = int(review.year)
            po_scan_domain += [('date_order', '>=', date(year, 1, 1)), ('date_order', '<', date(year + 1, 1, 1))]
        candidate_po_data = {}
        for po in self.env['purchase.order'].search(po_scan_domain):
            pdata = self._agent_po_retention_candidate_data(po, company)
            if pdata['retention_generated'] > 0 and pdata['fully_invoiced_by_amount']:
                retention_pos |= po
                candidate_po_data[po.id] = pdata

        # Build supplier control totals for all fully invoiced retention POs.
        generated_by_partner = defaultdict(float)
        po_count_by_partner = defaultdict(int)
        for po in retention_pos:
            pdata = candidate_po_data.get(po.id) or self._agent_po_retention_candidate_data(po, company)
            candidate_po_data[po.id] = pdata
            if pdata['fully_invoiced_by_amount'] and pdata['retention_generated'] > 0:
                pid = po.partner_id.commercial_partner_id.id
                generated_by_partner[pid] += pdata['retention_generated']
                po_count_by_partner[pid] += 1

        retention_plans_by_po = defaultdict(lambda: self.env['cash.plan.line'])
        retention_plans_without_po = self.env['cash.plan.line']
        for line in retention_plan_lines:
            if len(line.purchase_order_ids) == 1:
                retention_plans_by_po[line.purchase_order_ids.id] |= line
            else:
                retention_plans_without_po |= line

        # Existing retention plans linked to one PO.
        for po in retention_pos:
            pdata = candidate_po_data.get(po.id) or self._agent_po_retention_candidate_data(po, company)
            partner_id = po.partner_id.commercial_partner_id.id
            supplier_data = retention_data.get(partner_id, self._agent_empty_retention_data())
            supplier_open = max(supplier_data['net_due'], 0.0)
            generated_total = generated_by_partner.get(partner_id, 0.0)
            clear_allocation = generated_total <= supplier_open + company.currency_id.rounding
            open_for_po = min(pdata['retention_generated'], supplier_open) if clear_allocation else 0.0
            lines = retention_plans_by_po.get(po.id, self.env['cash.plan.line'])

            if lines:
                for line in lines:
                    if not pdata['fully_invoiced_by_amount']:
                        recommendations.append(self._agent_vals(
                            review, line, 'review',
                            _('Retention exists, but PO %(po)s is not yet fully invoiced by amount. PO untaxed: %(po_amount)s; gross posted invoiced work: %(inv)s. Do not release retention yet.') % {
                                'po': po.name,
                                'po_amount': format(pdata['po_amount'], ',.2f'),
                                'inv': format(pdata['gross_invoiced'], ',.2f'),
                            },
                            severity='warning', source_type='existing_retention', po=po,
                            bills=pdata['bills'], proposed=line.forecast_amount, can_apply=False,
                            aging=_('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        ))
                    elif not clear_allocation:
                        recommendations.append(self._agent_vals(
                            review, line, 'review',
                            _('PO %(po)s is fully invoiced and generated retention %(ret)s, but this supplier has several retention POs and the Retention Payable GL balance (%(open)s) is lower than total generated retention (%(total)s). The released amount cannot be allocated safely to a specific PO automatically.') % {
                                'po': po.name, 'ret': format(pdata['retention_generated'], ',.2f'),
                                'open': format(supplier_open, ',.2f'), 'total': format(generated_total, ',.2f'),
                            },
                            severity='warning', source_type='existing_retention', po=po,
                            bills=pdata['bills'], proposed=line.forecast_amount, can_apply=False,
                            aging=_('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        ))
                    elif company.currency_id.is_zero(open_for_po):
                        recommendations.append(self._agent_vals(
                            review, line, 'remove',
                            _('PO %s is fully invoiced, but no open retention remains in the Retention Payable GL for this supplier.') % po.name,
                            severity='warning', source_type='existing_retention', po=po,
                            bills=pdata['bills'], proposed=0.0,
                            can_apply=self._agent_safe_to_change(line),
                            aging=_('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        ))
                    elif company.currency_id.compare_amounts(line.forecast_amount, open_for_po) != 0:
                        recommendations.append(self._agent_vals(
                            review, line, 'update',
                            _('PO %(po)s is fully invoiced by amount. PO untaxed: %(po_amount)s; gross posted invoiced work: %(inv)s; retention generated by its bills: %(ret)s. Update planned retention to %(open)s based on the Retention Payable GL control.') % {
                                'po': po.name, 'po_amount': format(pdata['po_amount'], ',.2f'),
                                'inv': format(pdata['gross_invoiced'], ',.2f'),
                                'ret': format(pdata['retention_generated'], ',.2f'), 'open': format(open_for_po, ',.2f'),
                            },
                            severity='warning', source_type='existing_retention', po=po,
                            bills=pdata['bills'], proposed=open_for_po,
                            can_apply=self._agent_safe_to_change(line),
                            aging=_('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        ))
                    else:
                        recommendations.append(self._agent_vals(
                            review, line, 'keep',
                            _('PO %(po)s is fully invoiced by amount and its planned retention matches the retention cross-check. PO untaxed: %(po_amount)s; gross posted invoiced work: %(inv)s; retention generated: %(ret)s.') % {
                                'po': po.name, 'po_amount': format(pdata['po_amount'], ',.2f'),
                                'inv': format(pdata['gross_invoiced'], ',.2f'), 'ret': format(pdata['retention_generated'], ',.2f'),
                            },
                            source_type='existing_retention', po=po, bills=pdata['bills'],
                            proposed=line.forecast_amount, can_apply=False,
                            aging=_('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        ))
            else:
                # No retention plan exists for this PO: propose one only when the
                # amount-based invoicing test and GL cross-check are clear.
                if pdata['fully_invoiced_by_amount'] and pdata['retention_generated'] > 0 and clear_allocation and open_for_po > 0:
                    recommendations.append({
                        'review_id': review.id,
                        'agent_action': 'add',
                        'action': 'add',
                        'source_type': 'new_retention',
                        'severity': 'info',
                        'partner_id': po.partner_id.commercial_partner_id.id,
                        'purchase_order_id': po.id,
                        'bill_ids': [(6, 0, pdata['bills'].ids)],
                        'current_amount': 0.0,
                        'proposed_amount': min(pdata['retention_generated'], open_for_po),
                        'aging_summary': _('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        'reason': _('Add retention planned payment for %(po)s. PO untaxed amount %(po_amount)s is fully covered by gross posted invoiced work %(inv)s. Its bills generated retention %(ret)s, cross-checked against the supplier Retention Payable GL balance.') % {
                            'po': po.name, 'po_amount': format(pdata['po_amount'], ',.2f'),
                            'inv': format(pdata['gross_invoiced'], ',.2f'), 'ret': format(pdata['retention_generated'], ',.2f'),
                        },
                        'can_apply': True,
                    })
                elif pdata['fully_invoiced_by_amount'] and pdata['retention_generated'] > 0 and not clear_allocation:
                    recommendations.append({
                        'review_id': review.id,
                        'agent_action': 'review',
                        'action': 'review',
                        'source_type': 'new_retention',
                        'severity': 'warning',
                        'partner_id': po.partner_id.commercial_partner_id.id,
                        'purchase_order_id': po.id,
                        'bill_ids': [(6, 0, pdata['bills'].ids)],
                        'current_amount': 0.0,
                        'proposed_amount': pdata['retention_generated'],
                        'aging_summary': _('Supplier open retention GL: %s') % format(supplier_open, ',.2f'),
                        "reason": _("PO %s qualifies by invoice amount, but retention releases cannot be allocated safely among this supplier\'s multiple completed POs. Review before adding retention.") % po.name,
                        'can_apply': False,
                    })

        # Retention lines without exactly one PO cannot be matched to a PO-level
        # completion test, so keep them manual.
        for line in retention_plans_without_po:
            supplier_data = retention_data.get(line.partner_id.commercial_partner_id.id, self._agent_empty_retention_data()) if line.partner_id else self._agent_empty_retention_data()
            recommendations.append(self._agent_vals(
                review, line, 'review',
                _('Retention planned payment has no single PO reference, so the agent cannot perform the PO amount vs gross invoice completion test. Review manually.'),
                severity='warning', source_type='existing_retention', proposed=line.forecast_amount,
                bills=supplier_data['bills'], aging=supplier_data['aging_summary'], can_apply=False,
            ))

        po_ids_already_planned = set(po_plan_lines.mapped('purchase_order_ids').ids)

        # Review each payment linked to a Purchase Order (except retention). A PO
        # on a Supplier Balance / Account line is only a reference and never enters
        # this conversion logic.
        for line in po_plan_lines:
            pos = line.purchase_order_ids
            if len(pos) != 1:
                recommendations.append(self._agent_vals(
                    review, line, 'review',
                    _('This planned payment contains multiple POs. The agent will not automatically split or consolidate a multi-PO payment.'),
                    severity='warning', source_type='existing_po',
                ))
                continue

            po = pos[0]
            partner = po.partner_id.commercial_partner_id
            data = payable_data.get(partner.id, self._agent_empty_payable_data())
            posted_bills = self._agent_po_posted_bills(po)
            draft_bills = self._agent_po_draft_bills(po)
            due = self._agent_po_due_company_currency(po, company)

            if po.state not in ('purchase', 'done'):
                recommendations.append(self._agent_vals(
                    review, line, 'remove',
                    _('The linked PO %s is no longer a valid confirmed Purchase Order.') % po.name,
                    severity='danger', source_type='existing_po',
                    po=po, can_apply=self._agent_safe_to_change(line), proposed=0.0,
                ))
                continue

            if posted_bills:
                target = primary_balance.get(partner.id)
                can_convert = self._agent_safe_to_change(line)
                if target and not self._agent_safe_to_change(target):
                    can_convert = False
                if data['net_due'] <= 0:
                    recommendations.append(self._agent_vals(
                        review, line, 'remove',
                        _('PO %s now has posted vendor bill(s), but the supplier has no positive non-retention payable balance. Remove the obsolete PO-based plan.') % po.name,
                        severity='warning', source_type='existing_po', po=po,
                        bills=data['bills'], oldest_due=data['oldest_due'], aging=data['aging_summary'],
                        can_apply=self._agent_safe_to_change(line), proposed=0.0,
                    ))
                else:
                    recommendations.append(self._agent_vals(
                        review, line, 'convert',
                        _('PO %s now has posted vendor bill(s). Stop planning it as an uninvoiced PO and use the supplier payable balance instead. %s') % (po.name, data['aging_summary']),
                        severity='warning', source_type='existing_po', po=po,
                        bills=data['bills'], oldest_due=data['oldest_due'], aging=data['aging_summary'],
                        target=target, proposed=data['net_due'], can_apply=can_convert,
                    ))
                continue

            if draft_bills:
                recommendations.append(self._agent_vals(
                    review, line, 'review',
                    _('PO %s has draft vendor bill(s). They are not part of posted aging yet, so no automatic conversion is made.') % po.name,
                    severity='warning', source_type='existing_po', po=po,
                ))
                continue

            if getattr(po, 'invoice_status', False) != 'no':
                recommendations.append(self._agent_vals(
                    review, line, 'review',
                    _('PO %s is not currently "Nothing to Bill" and has no posted bill to move into aging. Review it manually.') % po.name,
                    severity='warning', source_type='existing_po', po=po,
                ))
                continue

            signature_note = self._agent_signature_note(po)
            if signature_note:
                recommendations.append(self._agent_vals(
                    review, line, 'review', signature_note,
                    severity='warning', source_type='existing_po', po=po,
                    proposed=line.forecast_amount,
                ))
                continue

            if due <= 0 or company.currency_id.is_zero(due):
                recommendations.append(self._agent_vals(
                    review, line, 'remove',
                    _('PO %s is still Nothing to Bill but its tracked remaining PO balance is zero. Remove the obsolete planned payment.') % po.name,
                    severity='warning', source_type='existing_po', po=po,
                    proposed=0.0, can_apply=self._agent_safe_to_change(line),
                ))
            elif company.currency_id.compare_amounts(line.forecast_amount, due) > 0:
                # Only reduce an installment when it exceeds what remains on the PO.
                # Never increase an existing installment to the full PO balance.
                recommendations.append(self._agent_vals(
                    review, line, 'update',
                    _('The planned installment is greater than the remaining PO balance. Reduce it from %s to %s. The agent never increases an existing DP/installment merely because the PO balance is higher.') %
                    (format(line.forecast_amount, ',.2f'), format(due, ',.2f')),
                    severity='warning', source_type='existing_po', po=po,
                    proposed=due, can_apply=self._agent_safe_to_change(line),
                ))
            else:
                recommendations.append(self._agent_vals(
                    review, line, 'keep',
                    _('PO %s is confirmed, Nothing to Bill, has no posted vendor bill, and the planned amount does not exceed its remaining PO balance%s.') %
                    (po.name, ' (' + format(due, ',.2f') + ')' if due else ''),
                    source_type='existing_po', po=po, proposed=line.forecast_amount,
                ))

        # Scan ALL confirmed Nothing-to-Bill POs, regardless of PO date. Missing ones are candidates.
        po_domain = [
            ('company_id', '=', company.id),
            ('state', 'in', ('purchase', 'done')),
            ('invoice_status', '=', 'no'),
        ]
        if review.year != 'all':
            year = int(review.year)
            po_domain += [('date_order', '>=', date(year, 1, 1)), ('date_order', '<', date(year + 1, 1, 1))]
        for po in self.env['purchase.order'].search(po_domain, order='date_order asc, id asc'):
            if po.id in po_ids_already_planned:
                continue
            if self._agent_po_posted_bills(po):
                continue
            due = self._agent_po_due_company_currency(po, company)
            if due <= 0 or company.currency_id.is_zero(due):
                continue
            signature_note = self._agent_signature_note(po)
            reason = _(
                'Confirmed PO %s is Nothing to Bill, has no posted vendor bill, and is missing from the current active payment plan. Remaining PO balance: %s. '
                'Because the agent cannot reliably infer DP/installment percentages from free-text payment terms, the amount must be reviewed before adding.'
            ) % (po.name, format(due, ',.2f'))
            action = 'review' if signature_note else 'add'
            if signature_note:
                reason = signature_note + ' ' + reason
            recommendations.append({
                'review_id': review.id,
                'action': action,
                'source_type': 'new_po',
                'severity': 'warning' if signature_note else 'info',
                'partner_id': po.partner_id.commercial_partner_id.id,
                'purchase_order_id': po.id,
                'current_amount': 0.0,
                'proposed_amount': due,
                'reason': reason,
                # New PO amounts are deliberately review-only because payment terms may be partial.
                'can_apply': False,
            })

        # Scan ALL live non-retention supplier payable balances, not only suppliers already planned.
        for partner_id, data in sorted(payable_data.items(), key=lambda item: (item[1]['oldest_due'] or date.max, item[0])):
            due = data['net_due']
            if due <= 0 or company.currency_id.is_zero(due):
                continue
            if partner_id in primary_balance:
                continue
            partner = self.env['res.partner'].browse(partner_id)
            # If a PO line for this supplier has been billed, its conversion recommendation will create/convert the balance line.
            convertible = po_plan_lines.filtered(
                lambda l: l.partner_id.commercial_partner_id.id == partner_id
                and len(l.purchase_order_ids) == 1
                and bool(self._agent_po_posted_bills(l.purchase_order_ids[0]))
            )
            if convertible:
                continue
            recommendations.append({
                'review_id': review.id,
                'action': 'add',
                'source_type': 'new_payable',
                'severity': 'info',
                'partner_id': partner.id,
                'bill_ids': [(6, 0, data['bills'].ids)],
                'current_amount': 0.0,
                'proposed_amount': due,
                'oldest_due_date': data['oldest_due'],
                'aging_summary': data['aging_summary'],
                'reason': _('Supplier has a positive current non-retention payable balance but no active supplier-balance planned payment. %s') % data['aging_summary'],
                'can_apply': True,
            })

        if recommendations:
            ReviewLine.create(recommendations)
        return len(recommendations)

    @api.model
    def _agent_plan_basis(self, line):
        """Classify a supplier planned payment using the actual data-entry rule.

        Retention is detected first because it is a separate liability. Otherwise,
        if a Purchase Order is linked, the payment is against that PO. If no PO is
        linked, the payment is against the supplier account / payable balance.
        """
        parts = [line.name or '', line.description or '']
        if line.category_id:
            parts.append(line.category_id.name or '')
        if line.account_id:
            parts.extend([line.account_id.code or '', line.account_id.name or ''])
        text = ' '.join(parts).lower()

        retention_tokens = ('retention', 'retainage', 'احتجاز', 'محتجز', 'ضمان')
        if any(token in text for token in retention_tokens):
            return 'retention'

        if line.purchase_order_ids:
            return 'po'
        return 'payable'

    @api.model
    def _agent_po_retention_candidate_data(self, po, company):
        """Calculate PO completion and generated retention without billing status.

        Completion compares the PO untaxed amount with gross posted invoice lines
        sourced from this PO's purchase lines. Retention is taken from Retention
        Payable journal lines on those same posted bills and proportionally allocated
        when a bill contains lines from more than one PO.
        """
        bills = po.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type in ('in_invoice', 'in_refund'))
        gross = 0.0
        retention_generated = 0.0
        relevant_bills = self.env['account.move']
        for move in bills:
            sign = 1.0 if move.move_type == 'in_invoice' else -1.0
            po_lines = move.invoice_line_ids.filtered(
                lambda l: not l.display_type and l.purchase_line_id and l.purchase_line_id.order_id == po
            )
            po_gross = sum(po_lines.mapped('price_subtotal')) * sign
            if company.currency_id.is_zero(po_gross):
                continue
            relevant_bills |= move
            gross += po_gross

            # If a bill mixes several POs, allocate its retention proportionally to
            # the gross source lines belonging to this PO.
            all_po_lines = move.invoice_line_ids.filtered(lambda l: not l.display_type and l.purchase_line_id)
            total_source = sum(all_po_lines.mapped('price_subtotal'))
            share = abs(po_gross) / abs(total_source) if total_source else 1.0
            retention_lines = move.line_ids.filtered(lambda l: self._agent_is_retention_account(l.account_id))
            move_retention = sum(-l.balance for l in retention_lines)
            retention_generated += move_retention * share

        po_amount = po.currency_id._convert(
            po.amount_untaxed,
            company.currency_id,
            company,
            po.date_order.date() if po.date_order else fields.Date.context_today(self),
        )
        # Allow normal currency rounding plus a tiny tolerance for legacy records.
        tolerance = max(company.currency_id.rounding, 0.02)
        fully_invoiced = gross + tolerance >= po_amount and po_amount > 0
        return {
            'po_amount': po_amount,
            'gross_invoiced': gross,
            'retention_generated': max(retention_generated, 0.0),
            'fully_invoiced_by_amount': fully_invoiced,
            'bills': relevant_bills,
        }

    @api.model
    def _agent_get_retention_data(self, company):
        """Return the live retention liability by supplier from the retention GL account.

        Retention account 201019 is a normal liability control account in this database, not
        necessarily a reconcilable ``liability_payable`` account.  Therefore ``amount_residual``
        and ``reconciled`` are NOT reliable here.  The correct source is the posted GL balance:
        credits increase retention payable and debits/releases reduce it.
        """
        aml = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'),
            ('partner_id', '!=', False),
        ])
        aml = aml.filtered(lambda line: self._agent_is_retention_account(line.account_id))
        aml = aml.filtered(lambda line: not company.currency_id.is_zero(line.balance))

        grouped = {}
        for line in aml:
            partner = line.partner_id.commercial_partner_id
            data = grouped.setdefault(partner.id, {
                'net_due': 0.0,
                'bills': self.env['account.move'],
                'oldest_due': False,
            })
            # Odoo company-currency balance: credits are negative, debits positive.
            # A positive retention liability is therefore the negative net GL balance.
            data['net_due'] += -line.balance
            move = line.move_id
            if move.move_type in ('in_invoice', 'in_refund') and move.state == 'posted':
                data['bills'] |= move
                due_date = line.date_maturity or move.invoice_date_due or move.date
                if due_date and (not data['oldest_due'] or due_date < data['oldest_due']):
                    data['oldest_due'] = due_date

        for data in grouped.values():
            data['aging_summary'] = _('Open retention liability: %s') % format(max(data['net_due'], 0.0), ',.2f')
        return grouped

    @api.model
    def _agent_empty_retention_data(self):
        return {
            'net_due': 0.0,
            'bills': self.env['account.move'],
            'oldest_due': False,
            'aging_summary': _('Open retention liability: 0.00'),
        }

    @api.model
    def _agent_get_payable_data(self, company):
        """Return live supplier payable balances and aging directly from posted journal items.

        The balance includes open debit/credit items on payable accounts so supplier advances
        reduce the amount due. Retention payable is intentionally excluded from normal payment
        planning. Aging buckets use maturity date (then invoice due date, then accounting date).
        """
        aml = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'liability_payable'),
            ('partner_id', '!=', False),
            ('reconciled', '=', False),
        ])
        aml = aml.filtered(lambda line: not company.currency_id.is_zero(line.amount_residual))
        aml = aml.filtered(lambda line: not self._agent_is_retention_account(line.account_id))

        today = fields.Date.context_today(self)
        grouped = {}
        for line in aml:
            partner = line.partner_id.commercial_partner_id
            data = grouped.setdefault(partner.id, {
                'net_due': 0.0,
                'bills': self.env['account.move'],
                'oldest_due': False,
                'bucket_amounts': {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, '90_plus': 0.0},
            })
            # Payable credits normally carry a negative residual; open debit advances carry
            # a positive residual and therefore reduce the supplier amount due.
            data['net_due'] += -line.amount_residual

            move = line.move_id
            if move.move_type not in ('in_invoice', 'in_refund'):
                continue
            if move.state != 'posted':
                continue
            if move.move_type == 'in_invoice' and line.amount_residual < 0:
                bill_amount = -line.amount_residual
                due_date = line.date_maturity or move.invoice_date_due or move.date
                if due_date:
                    if not data['oldest_due'] or due_date < data['oldest_due']:
                        data['oldest_due'] = due_date
                    overdue = (today - due_date).days
                    if overdue <= 0:
                        bucket = 'current'
                    elif overdue <= 30:
                        bucket = '1_30'
                    elif overdue <= 60:
                        bucket = '31_60'
                    elif overdue <= 90:
                        bucket = '61_90'
                    else:
                        bucket = '90_plus'
                    data['bucket_amounts'][bucket] += bill_amount
                data['bills'] |= move
            elif move.move_type == 'in_refund':
                data['bills'] |= move

        for data in grouped.values():
            b = data['bucket_amounts']
            data['aging_summary'] = _(
                'Net due: %(net)s | Not due: %(current)s | 1-30: %(b1)s | 31-60: %(b2)s | 61-90: %(b3)s | 90+: %(b4)s'
            ) % {
                'net': format(max(data['net_due'], 0.0), ',.2f'),
                'current': format(b['current'], ',.2f'),
                'b1': format(b['1_30'], ',.2f'),
                'b2': format(b['31_60'], ',.2f'),
                'b3': format(b['61_90'], ',.2f'),
                'b4': format(b['90_plus'], ',.2f'),
            }
        return grouped

    @api.model
    def _agent_empty_payable_data(self):
        return {
            'net_due': 0.0,
            'bills': self.env['account.move'],
            'oldest_due': False,
            'aging_summary': _('Net due: 0.00'),
        }

    @api.model
    def _agent_is_retention_account(self, account):
        code = (account.code or '').strip().lower()
        name = (account.name or '').strip().lower()
        return code == '201019' or 'retention' in name or 'retention' in code or 'احتجاز' in name

    @api.model
    def _agent_po_posted_bills(self, po):
        return po.invoice_ids.filtered(lambda m: m.state == 'posted' and m.move_type in ('in_invoice', 'in_refund'))

    @api.model
    def _agent_po_draft_bills(self, po):
        return po.invoice_ids.filtered(lambda m: m.state == 'draft' and m.move_type in ('in_invoice', 'in_refund'))

    @api.model
    def _agent_po_due_company_currency(self, po, company):
        due = max(getattr(po, 'amount_paid_residual', 0.0), 0.0)
        return po.currency_id._convert(
            due,
            company.currency_id,
            company,
            fields.Date.context_today(self),
        )

    @api.model
    def _agent_signature_note(self, po):
        if 'signature_state' not in po._fields:
            return False
        state = po.signature_state
        # Common signed values across the ABSAR signing modules. Unknown/non-final states are review-only.
        if not state or state in ('signed', 'direct_signed', 'completed', 'done'):
            return False
        label = dict(po._fields['signature_state'].selection).get(state, state) if po._fields['signature_state'].selection else state
        return _('PO %s signing workflow is not complete (%s).') % (po.name, label)

    @api.model
    def _agent_safe_to_change(self, line):
        return bool(
            line
            and line.state == 'planned'
            and getattr(line, 'ceo_decision', 'not_sent') == 'not_sent'
            and not line.is_unplanned
        )

    @api.model
    def _agent_vals(self, review, line, action, reason, severity='info', proposed=None,
                    can_apply=False, source_type=False, po=False, target=False,
                    bills=False, oldest_due=False, aging=False):
        partner = line.partner_id.commercial_partner_id if line and line.partner_id else (po.partner_id.commercial_partner_id if po else False)
        return {
            'review_id': review.id,
            'agent_action': action,
            'action': action,
            'source_type': source_type,
            'severity': severity,
            'partner_id': partner.id if partner else False,
            'plan_line_id': line.id if line else False,
            'target_plan_line_id': target.id if target else False,
            'purchase_order_id': po.id if po else (line.purchase_order_ids[:1].id if line and len(line.purchase_order_ids) == 1 else False),
            'bill_ids': [(6, 0, bills.ids)] if bills else False,
            'current_amount': line.forecast_amount if line else 0.0,
            'proposed_amount': line.forecast_amount if proposed is None and line else (proposed or 0.0),
            'oldest_due_date': oldest_due or False,
            'aging_summary': aging or False,
            'reason': reason,
            'can_apply': bool(can_apply),
        }
