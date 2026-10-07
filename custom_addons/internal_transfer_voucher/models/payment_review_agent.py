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
        help='Filters dated existing plans and new PO candidates. Undated active plans remain visible. Duplicate and retention controls always include all years; supplier aging remains the full live open balance.',
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
            rec.selected_count = len(rec.line_ids.filtered(lambda l: l.apply and not l.applied))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = _('Payment Review %s') % fields.Date.context_today(self)
        return super().create(vals_list)

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
        # Optional signing fields and journal balances have no universal stored
        # dependency. Refresh eligibility when opening an existing snapshot.
        self.line_ids._compute_can_apply()
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
        safe = self.line_ids.filtered(lambda l: l._decision_is_safely_applicable())
        (self.line_ids - safe).write({'apply': False})
        safe.write({'apply': True})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_clear_selection(self):
        self.ensure_one()
        self.line_ids.filtered('apply').write({'apply': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_apply_selected(self):
        self.ensure_one()
        selected = self.line_ids.filtered(lambda l: l.apply and not l.applied)
        return selected.action_apply_selected_from_list()



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
    amount_confirmed = fields.Boolean(
        string='Amount Reviewed', default=False,
        help='For a new PO payment, confirm the installment/advance amount before applying. The full remaining PO amount is only a suggestion.',
    )
    can_apply = fields.Boolean(compute='_compute_can_apply', store=True, readonly=True)
    applied = fields.Boolean(default=False, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.pop('can_apply', None)
            if vals.get('action') and not vals.get('agent_action'):
                vals['agent_action'] = vals['action']
        return super().create(vals_list)

    @api.depends(
        'action', 'source_type', 'proposed_amount', 'amount_confirmed', 'applied',
        'partner_id', 'plan_line_id.state', 'plan_line_id.ceo_decision',
        'plan_line_id.is_unplanned', 'target_plan_line_id.state',
        'target_plan_line_id.ceo_decision', 'target_plan_line_id.is_unplanned',
        'purchase_order_id.state', 'purchase_order_id.invoice_status',
        'purchase_order_id.invoice_ids.state',
        'review_id.company_id',
    )
    def _compute_can_apply(self):
        for rec in self:
            rec.can_apply = rec._decision_is_safely_applicable()

    @api.onchange('proposed_amount')
    def _onchange_manual_amount(self):
        for rec in self:
            if rec.source_type == 'new_po':
                rec.amount_confirmed = False

    def write(self, vals):
        # A changed installment must be confirmed again, even through import/RPC.
        if 'proposed_amount' in vals and 'amount_confirmed' not in vals:
            po_rows = self.filtered(lambda l: l.source_type == 'new_po')
            if po_rows:
                super(CashPlanReviewLine, po_rows).write({'amount_confirmed': False})
        return super().write(vals)

    def _decision_is_safely_applicable(self):
        self.ensure_one()
        if self.applied or self.action in ('keep', 'review'):
            return False
        if not self.partner_id:
            return False
        if self.action == 'add':
            if self.source_type == 'new_payable':
                return self.proposed_amount > 0 and bool(self.partner_id)
            if self.source_type == 'new_po':
                po = self.purchase_order_id
                return bool(self.amount_confirmed and self._eligible_new_po(po) and self.proposed_amount > 0)
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
        if not self._decision_is_safely_applicable():
            raise UserError(_('This recommendation is not currently safe to apply automatically. Change the decision/amount or review it manually.'))
        self.apply = not self.apply
        return {'type': 'ir.actions.client', 'tag': 'reload'}


    def action_apply_selected_from_list(self):
        if not self:
            raise UserError(_('Select at least one recommendation first.'))
        reviews = self.mapped('review_id')
        if len(reviews) != 1:
            raise UserError(_('Apply recommendations from one Payment Review at a time.'))
        unsafe = self.filtered(lambda l: not l._decision_is_safely_applicable())
        if unsafe:
            labels = []
            for line in unsafe[:8]:
                note = _(' — confirm Amount Reviewed after checking the PO installment') if line.source_type == 'new_po' and not line.amount_confirmed else ''
                labels.append('%s - %s%s' % (line.partner_id.display_name or _('No Supplier'), dict(line._fields['action'].selection).get(line.action, line.action), note))
            raise UserError(_('Selected recommendations cannot be applied:\n- %s\nReview the decision, amount, and current payment/PO state. No selected changes were applied.') % '\n- '.join(labels))
        # A transaction error rolls back every selected mutation; no partial success is hidden.
        for line in self:
            line._apply_recommendation()
        self.write({'apply': False})
        remaining = reviews.line_ids.filtered(lambda l: not l.applied and l._decision_is_safely_applicable())
        reviews.state = 'partial' if remaining else 'applied'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Payment Review'),
                'message': _('%s selected recommendation(s) applied successfully.') % len(self),
                'type': 'success', 'sticky': False,
                'next': reviews.action_open_recommendations(),
            },
        }

    def _eligible_new_po(self, po):
        agent = self.env['cash.plan.line']
        return bool(
            po and po.company_id == self.review_id.company_id
            and po.state in ('purchase', 'done') and po.invoice_status == 'no'
            and not agent._agent_signature_note(po)
            and not agent._agent_po_posted_bills(po)
            and not agent._agent_po_draft_bills(po)
        )

    def _active_supplier_plans(self):
        return self.env['cash.plan.line'].search([
            ('company_id', '=', self.review_id.company_id.id),
            ('flow_type', '=', 'out'), ('transaction_type', '=', 'supplier'),
            ('partner_id.commercial_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('state', 'not in', ('executed', 'cancel')),
        ])

    def _validate_live_recommendation(self):
        """Reject snapshots whose liability, source, or coverage has changed."""
        agent = self.env['cash.plan.line']
        company = self.review_id.company_id
        po = self.purchase_order_id
        line = self.plan_line_id
        if line and (line.company_id != company or line.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id):
            raise UserError(_('The planned payment supplier/company changed. Run a new review.'))
        if line and self.source_type in ('existing_po', 'existing_retention') and line.purchase_order_ids != po:
            raise UserError(_('The planned payment PO reference changed. Run a new review.'))
        if po and po.company_id != company:
            raise UserError(_('The purchase order belongs to another company.'))
        if self.partner_id and line:
            expected_basis = {'existing_po': 'po', 'existing_payable': 'payable', 'existing_retention': 'retention'}.get(self.source_type)
            if expected_basis and agent._agent_plan_basis(line) != expected_basis:
                raise UserError(_('The planned payment basis changed or it was already converted. Run a new review.'))
        if self.source_type in ('new_payable', 'existing_payable') or self.action == 'convert':
            data = agent._agent_get_payable_data(company).get(self.partner_id.commercial_partner_id.id, agent._agent_empty_payable_data())
            if self.action in ('add', 'update', 'convert'):
                if company.currency_id.compare_amounts(self.proposed_amount, max(data['net_due'], 0.0)):
                    raise UserError(_('The supplier payable balance changed or the proposed amount differs from the current balance. Run a new review.'))
                self.bill_ids = [(6, 0, data['bills'].ids)]
            if self.action == 'remove' and self.agent_action == 'remove':
                others = (self._active_supplier_plans() - line).filtered(lambda l: agent._agent_plan_basis(l) == 'payable')
                if data['net_due'] > 0 and not others:
                    raise UserError(_('This supplier still has a positive payable balance and no other balance plan. Run a new review.'))
        if self.source_type in ('new_retention', 'existing_retention'):
            if not po or len(line.purchase_order_ids) > 1:
                raise UserError(_('Retention requires one unambiguous PO reference.'))
            same_po = self._active_supplier_plans().filtered(
                lambda l: agent._agent_plan_basis(l) == 'retention' and l.purchase_order_ids == po
            )
            if self.action != 'remove' and self.source_type == 'existing_retention' and len(same_po) > 1:
                raise UserError(_('Multiple retention payments cover this PO. Resolve their combined amount before updating one payment.'))
            controls = agent._agent_retention_controls(company)
            pdata = controls['po_data'].get(po.id) or agent._agent_po_retention_candidate_data(po, company)
            clear, amount = agent._agent_retention_allocation(po, pdata, controls, company)
            if not clear or (self.action != 'remove' and not pdata['fully_invoiced_by_amount']):
                raise UserError(_('Current posted invoices / account 201019 do not support a safe retention allocation. Run a new review.'))
            expected = 0.0 if self.action == 'remove' else amount
            if (self.action == 'remove' and not company.currency_id.is_zero(amount)) or company.currency_id.compare_amounts(self.proposed_amount, expected):
                raise UserError(_('The open PO retention differs from this recommendation. Run a new review.'))
            self.bill_ids = [(6, 0, pdata['bills'].ids)]
            if self.source_type == 'new_retention':
                if po.state not in ('purchase', 'done'):
                    raise UserError(_('A new retention plan requires a confirmed PO.'))
                floating = self._active_supplier_plans().filtered(lambda l: agent._agent_plan_basis(l) == 'retention' and len(l.purchase_order_ids) != 1)
                if floating:
                    raise UserError(_('An existing retention plan has no single PO allocation. Resolve it before adding PO retention.'))
        if self.source_type == 'new_po':
            if not self._eligible_new_po(po):
                raise UserError(_('The PO is unsigned, billed, has a draft bill, or is no longer eligible. Run a new review.'))
            due = agent._agent_po_due_company_currency(po, company)
            if company.currency_id.compare_amounts(self.proposed_amount, due) > 0:
                raise UserError(_('The proposed installment exceeds the current remaining PO balance.'))
        if self.action == 'convert':
            if not po or not agent._agent_po_posted_bills(po):
                raise UserError(_('This PO no longer has posted vendor bills. Run a new review.'))
            if not agent._agent_po_retention_candidate_data(po, company)['fully_invoiced_by_amount']:
                raise UserError(_('This PO is only partially invoiced by amount. Review its remaining uninvoiced obligation before converting.'))
        if self.source_type == 'existing_po' and self.action == 'update':
            if not self._eligible_new_po(po) or company.currency_id.compare_amounts(self.proposed_amount, agent._agent_po_due_company_currency(po, company)) > 0:
                raise UserError(_('The PO is no longer eligible or the proposed amount exceeds its remaining balance. Run a new review.'))
        if self.source_type == 'existing_po' and self.action == 'remove' and self.agent_action == 'remove':
            due = agent._agent_po_due_company_currency(po, company) if po else 0.0
            payable = agent._agent_get_payable_data(company).get(self.partner_id.commercial_partner_id.id, agent._agent_empty_payable_data())
            if po and po.state in ('purchase', 'done') and due > 0 and not (agent._agent_po_posted_bills(po) and payable['net_due'] <= 0):
                raise UserError(_('The PO still has an outstanding obligation. Run a new review.'))

    def _apply_recommendation(self):
        self.ensure_one()
        if not self._decision_is_safely_applicable():
            raise UserError(_('This recommendation is already applied, review-only, unconfirmed, or locked. No change was applied.'))
        # Serialize agent mutations for one supplier; re-query duplicate targets afterwards.
        if self.partner_id:
            self.env.cr.execute('SELECT id FROM res_partner WHERE id = %s FOR UPDATE', [self.partner_id.commercial_partner_id.id])
        self._validate_live_recommendation()

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
            targets = (self._active_supplier_plans() - line).filtered(
                lambda l: self.env['cash.plan.line']._agent_plan_basis(l) == 'payable'
            )
            if len(targets) > 1:
                raise UserError(_('Multiple supplier-balance plans exist. Resolve duplicates and run a new review.'))
            target = targets[:1]
            self.target_plan_line_id = target
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
                    'purchase_order_ids': [(5, 0, 0)],
                    'bill_ids': [(6, 0, self.bill_ids.ids)],
                    'forecast_amount': self.proposed_amount,
                })

        elif self.action == 'add' and self.source_type == 'new_po':
            po = self.purchase_order_id
            if not self.amount_confirmed or not self._eligible_new_po(po):
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
            if not retention_account:
                raise UserError(_('Account 201019 Retention Payable is missing for this company.'))
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
            candidates = self._active_supplier_plans()
            existing = candidates.filtered(lambda l: self.env['cash.plan.line']._agent_plan_basis(l) == 'payable')[:1]
            if existing:
                raise UserError(_('A supplier-balance planned payment now exists for %s. Run a new review.') % self.partner_id.display_name)

            if candidates.filtered(lambda l: self.env['cash.plan.line']._agent_plan_basis(l) == 'po' and len(l.purchase_order_ids) > 1):
                raise UserError(_('An active multi-PO payment may already cover these bills. Consolidate it before adding a supplier-balance plan.'))
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
            planned_domain += ['|', ('planned_date', '=', False), '&', ('planned_date', '>=', date(year, 1, 1)), ('planned_date', '<=', date(year, 12, 31))]
        all_planned = self.search([
            ('company_id', '=', company.id), ('flow_type', '=', 'out'),
            ('state', 'not in', ('executed', 'cancel')),
        ])
        planned = self.search(planned_domain)
        all_supplier_lines = all_planned.filtered(lambda l: l.transaction_type == 'supplier')
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
        for line in all_supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'payable'):
            balance_by_partner[line.partner_id.commercial_partner_id.id] |= line

        primary_balance = {}
        for partner_id, lines in balance_by_partner.items():
            # Prefer a draft/not-sent line because it can be maintained automatically.
            # Preserve a locked/approved obligation; cancel editable duplicates instead.
            ordered = lines.sorted(key=lambda l: (1 if self._agent_safe_to_change(l) else 0, l.id))
            primary = ordered[:1]
            if primary:
                primary_balance[partner_id] = primary
            for duplicate in ordered[1:]:
                if duplicate not in planned:
                    continue
                recommendations.append(self._agent_vals(
                    review, duplicate, 'remove',
                    _('Duplicate supplier-balance planned payment. Keep one balance line per supplier to avoid double planning.'),
                    severity='danger',
                    source_type='existing_payable',
                    can_apply=self._agent_safe_to_change(duplicate),
                ))

        # Review existing supplier-balance planned payments against live open payables.
        for partner_id, line in primary_balance.items():
            if line not in planned:
                continue
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
        controls = self._agent_retention_controls(company)
        candidate_po_data = controls['po_data']
        for po in self.env['purchase.order'].search(po_scan_domain):
            pdata = candidate_po_data.get(po.id) or self._agent_po_retention_candidate_data(po, company)
            if pdata['retention_generated'] > 0 and pdata['fully_invoiced_by_amount']:
                retention_pos |= po

        retention_plans_by_po = defaultdict(lambda: self.env['cash.plan.line'])
        retention_plans_without_po = self.env['cash.plan.line']
        for line in all_supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'retention'):
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
            generated_total = controls['generated_by_partner'].get(partner_id, 0.0)
            clear_allocation, open_for_po = self._agent_retention_allocation(po, pdata, controls, company)
            lines = retention_plans_by_po.get(po.id, self.env['cash.plan.line'])

            if lines:
                for line in lines:
                    if line not in planned:
                        continue
                    if len(lines) > 1 and not company.currency_id.is_zero(open_for_po):
                        recommendations.append(self._agent_vals(
                            review, line, 'review',
                            _('Multiple retention payments cover PO %s. Review their combined amount; do not assign the entire PO retention to each payment.') % po.name,
                            severity='warning', source_type='existing_retention', po=po,
                            bills=pdata['bills'], proposed=line.forecast_amount,
                        ))
                    elif not pdata['fully_invoiced_by_amount']:
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
                            _('PO %(po)s is fully invoiced and generated retention %(ret)s. Supplier Retention Payable GL: %(open)s; total generated: %(total)s. Mixed invoice sources or retention releases prevent a safe allocation to this PO.') % {
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
                floating = retention_plans_without_po.filtered(lambda l: l.partner_id.commercial_partner_id.id == partner_id)
                if floating:
                    recommendations.append({
                        'review_id': review.id, 'action': 'review', 'source_type': 'new_retention',
                        'partner_id': po.partner_id.commercial_partner_id.id, 'purchase_order_id': po.id,
                        'proposed_amount': pdata['retention_generated'],
                        'reason': _('An existing retention plan has no single PO allocation. Resolve it before adding PO retention.'),
                    })
                    continue
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
            if line not in planned:
                continue
            supplier_data = retention_data.get(line.partner_id.commercial_partner_id.id, self._agent_empty_retention_data()) if line.partner_id else self._agent_empty_retention_data()
            recommendations.append(self._agent_vals(
                review, line, 'review',
                _('Retention planned payment has no single PO reference, so the agent cannot perform the PO amount vs gross invoice completion test. Review manually.'),
                severity='warning', source_type='existing_retention', proposed=line.forecast_amount,
                bills=supplier_data['bills'], aging=supplier_data['aging_summary'], can_apply=False,
            ))

        po_ids_already_planned = set(all_supplier_lines.mapped('purchase_order_ids').ids)

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
                if not self._agent_po_retention_candidate_data(po, company)['fully_invoiced_by_amount']:
                    recommendations.append(self._agent_vals(
                        review, line, 'review',
                        _('PO %s has posted bills but is only partially invoiced by amount. Review the remaining uninvoiced obligation before replacing its PO plan with supplier aging.') % po.name,
                        source_type='existing_po', po=po, proposed=line.forecast_amount,
                    ))
                    continue
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
            if self._agent_po_posted_bills(po) or self._agent_po_draft_bills(po):
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
            multi_po = all_supplier_lines.filtered(lambda l: l.partner_id.commercial_partner_id.id == partner_id and self._agent_plan_basis(l) == 'po' and len(l.purchase_order_ids) > 1)
            if multi_po:
                recommendations.append({
                    'review_id': review.id, 'action': 'review', 'source_type': 'new_payable',
                    'partner_id': partner.id, 'proposed_amount': due,
                    'reason': _('An active multi-PO payment may already cover this supplier liability. Consolidate the existing payment before adding a supplier-balance plan.'),
                    'aging_summary': data['aging_summary'], 'can_apply': False,
                })
                continue
            # If a PO line for this supplier has been billed, its conversion recommendation will create/convert the balance line.
            convertible = all_supplier_lines.filtered(lambda l: self._agent_plan_basis(l) == 'po').filtered(
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
        if line.account_id and (line.account_id.code or '').strip() == '201019':
            return 'retention'
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
        """Use posted product lines and account 201019; never PO Billing Status."""
        bills = self._agent_po_posted_bills(po)
        gross = gross_po_currency = retention_generated = 0.0
        allocation_clear = True
        relevant_bills = self.env['account.move']
        for move in bills:
            products = move.invoice_line_ids.filtered(
                lambda l: l.display_type in (False, 'product') and not self._agent_is_retention_account(l.account_id)
            )
            source_lines = products.filtered(lambda l: l.purchase_line_id)
            po_lines = source_lines.filtered(lambda l: l.purchase_line_id.order_id == po)
            if not po_lines:
                continue
            relevant_bills |= move
            sign = -1.0 if move.move_type == 'in_refund' else 1.0
            # balance is already signed company currency (tax excluded).
            gross += sum(po_lines.mapped('balance'))
            po_subtotal = sum(po_lines.mapped('price_subtotal')) * sign
            gross_po_currency += move.currency_id._convert(
                po_subtotal, po.currency_id, company, move.invoice_date or move.date,
            )
            retention_lines = move.line_ids.filtered(lambda l: self._agent_is_retention_account(l.account_id))
            if not retention_lines:
                continue
            source_pos = source_lines.mapped('purchase_line_id.order_id')
            unlinked_work = products.filtered(lambda l: not l.purchase_line_id and not company.currency_id.is_zero(l.balance))
            if len(source_pos) == 1 and not unlinked_work:
                retention_generated += sum(-l.balance for l in retention_lines)
            elif all(l.purchase_line_id for l in retention_lines):
                retention_generated += sum(-l.balance for l in retention_lines if l.purchase_line_id.order_id == po)
            else:
                # Different POs may have different retention rates. Never invent an allocation.
                allocation_clear = False
                total_source = sum(abs(l.balance) for l in source_lines)
                share = sum(abs(l.balance) for l in po_lines) / total_source if total_source else 0.0
                retention_generated += sum(-l.balance for l in retention_lines) * share
        po_amount = po.currency_id._convert(
            po.amount_untaxed, company.currency_id, company,
            po.date_order.date() if po.date_order else fields.Date.context_today(self),
        )
        tolerance = max(po.currency_id.rounding, 0.02)
        return {
            'po_amount': po_amount, 'gross_invoiced': gross,
            'retention_generated': max(retention_generated, 0.0),
            'fully_invoiced_by_amount': gross_po_currency + tolerance >= po.amount_untaxed and po.amount_untaxed > 0,
            'allocation_clear': allocation_clear, 'bills': relevant_bills,
        }

    @api.model
    def _agent_retention_controls(self, company):
        po_data = {}
        generated = defaultdict(float)
        counts = defaultdict(int)
        ambiguous = set()
        for po in self.env['purchase.order'].search([('company_id', '=', company.id)]):
            pdata = self._agent_po_retention_candidate_data(po, company)
            po_data[po.id] = pdata
            if pdata['retention_generated'] > 0:
                pid = po.partner_id.commercial_partner_id.id
                generated[pid] += pdata['retention_generated']
                counts[pid] += 1
                if not pdata['allocation_clear']:
                    ambiguous.add(pid)
        return {'po_data': po_data, 'generated_by_partner': generated,
                'po_count_by_partner': counts, 'ambiguous_partners': ambiguous,
                'retention_data': self._agent_get_retention_data(company)}

    @api.model
    def _agent_retention_allocation(self, po, pdata, controls, company):
        pid = po.partner_id.commercial_partner_id.id
        open_amount = max(controls['retention_data'].get(pid, {}).get('net_due', 0.0), 0.0)
        if not pdata['allocation_clear'] or pid in controls['ambiguous_partners']:
            return False, 0.0
        if company.currency_id.is_zero(open_amount):
            return True, 0.0
        total = controls['generated_by_partner'].get(pid, 0.0)
        count = controls['po_count_by_partner'].get(pid, 0)
        if count == 1 or total <= open_amount + company.currency_id.rounding:
            return True, min(pdata['retention_generated'], open_amount)
        # Partial releases with several retention POs have no reliable PO allocation.
        return False, 0.0

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
                'credit_offsets': 0.0,
                'bills': self.env['account.move'],
                'oldest_due': False,
                'bucket_amounts': {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, '90_plus': 0.0},
            })
            # Payable credits normally carry a negative residual; open debit advances carry
            # a positive residual and therefore reduce the supplier amount due.
            data['net_due'] += -line.amount_residual
            if line.amount_residual > 0:
                data['credit_offsets'] += line.amount_residual

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
                'Net balance: %(net)s | Advances/credits: %(offset)s | Gross unpaid invoices — Not due: %(current)s | 1-30: %(b1)s | 31-60: %(b2)s | 61-90: %(b3)s | 90+: %(b4)s'
            ) % {
                'net': format(data['net_due'], ',.2f'),
                'offset': format(data['credit_offsets'], ',.2f'),
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
        return code == '201019'

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
            and getattr(line, 'ceo_decision', 'not_sent') in ('not_sent', 'pending', 'held', 'rejected', False)
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
