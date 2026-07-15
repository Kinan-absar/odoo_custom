from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CashPlanRunCEO(models.Model):
    _inherit = 'cash.plan.run'

    ceo_reviewed_by = fields.Many2one('res.users', string='CEO Reviewed By', readonly=True, copy=False, tracking=True)
    ceo_reviewed_date = fields.Datetime(string='CEO Reviewed On', readonly=True, copy=False, tracking=True)
    ceo_comment = fields.Text(string='CEO Plan Comment', tracking=True)
    ceo_pending_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    ceo_approved_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    ceo_rejected_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    approved_inflow = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_outflow = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_net = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_closing = fields.Monetary(compute='_compute_ceo_summary', store=True)

    @api.depends('opening_balance', 'line_ids.ceo_decision', 'line_ids.approved_amount', 'line_ids.flow_type', 'line_ids.state')
    def _compute_ceo_summary(self):
        for run in self:
            lines = run.line_ids.filtered(lambda line: line.state != 'cancel')
            run.ceo_pending_count = len(lines.filtered(lambda line: line.ceo_decision == 'pending'))
            run.ceo_approved_count = len(lines.filtered(lambda line: line.ceo_decision in ('approved', 'adjusted')))
            run.ceo_rejected_count = len(lines.filtered(lambda line: line.ceo_decision == 'rejected'))
            approved = lines.filtered(lambda line: line.ceo_decision in ('approved', 'adjusted'))
            run.approved_inflow = sum(approved.filtered(lambda line: line.flow_type == 'in').mapped('approved_amount'))
            run.approved_outflow = sum(approved.filtered(lambda line: line.flow_type == 'out').mapped('approved_amount'))
            run.approved_net = run.approved_inflow - run.approved_outflow
            run.approved_closing = run.opening_balance + run.approved_net

    def action_submit(self):
        for run in self:
            if not run.line_ids.filtered(lambda line: line.state != 'cancel'):
                raise UserError(_('Add at least one planned cash movement before submitting.'))
            run.line_ids.filtered(lambda line: line.state != 'cancel').write({
                'ceo_decision': 'pending',
                'approved_amount': 0.0,
                'ceo_comment': False,
                'ceo_approved_by': False,
                'ceo_approved_date': False,
            })
            run.write({'state': 'submitted', 'ceo_reviewed_by': False, 'ceo_reviewed_date': False})
        return True

    def action_approve(self):
        for run in self:
            pending = run.line_ids.filtered(lambda line: line.state != 'cancel' and line.ceo_decision == 'pending')
            if pending:
                raise UserError(_('All planned movements must be reviewed by the CEO before approving the weekly plan.'))
            approved = run.line_ids.filtered(lambda line: line.state != 'cancel' and line.ceo_decision in ('approved', 'adjusted'))
            if not approved:
                raise UserError(_('At least one planned movement must be approved.'))
            run.write({
                'state': 'approved',
                'ceo_reviewed_by': run.ceo_reviewed_by.id or self.env.user.id,
                'ceo_reviewed_date': run.ceo_reviewed_date or fields.Datetime.now(),
            })
        return True


class CashPlanLineCEO(models.Model):
    _inherit = 'cash.plan.line'

    approved_amount = fields.Monetary(string='CEO Approved Amount', tracking=True, copy=False)
    ceo_decision = fields.Selection([
        ('pending', 'Pending CEO Review'),
        ('approved', 'Approved'),
        ('adjusted', 'Approved with Adjustment'),
        ('rejected', 'Rejected'),
    ], default='pending', required=True, tracking=True, copy=False)
    ceo_comment = fields.Text(string='CEO Comment', tracking=True, copy=False)
    ceo_approved_by = fields.Many2one('res.users', string='CEO Reviewed By', readonly=True, copy=False)
    ceo_approved_date = fields.Datetime(string='CEO Reviewed On', readonly=True, copy=False)
    execution_amount = fields.Monetary(string='Execution Amount', compute='_compute_execution_amount', store=True)

    @api.depends('forecast_amount', 'approved_amount', 'ceo_decision')
    def _compute_execution_amount(self):
        for line in self:
            line.execution_amount = line.approved_amount if line.ceo_decision in ('approved', 'adjusted') else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.run_id.state == 'draft':
                record.approved_amount = 0.0
                record.ceo_decision = 'pending'
        return records

    def action_ceo_decide(self, decision, approved_amount=None, comment=None, reviewer=None):
        if decision not in ('approved', 'adjusted', 'rejected'):
            raise ValidationError(_('Invalid CEO decision.'))
        reviewer = reviewer or self.env.user
        for line in self:
            if line.run_id.state != 'submitted':
                raise UserError(_('Only submitted weekly plans can be reviewed.'))
            amount = 0.0
            if decision != 'rejected':
                amount = line.forecast_amount if approved_amount is None else float(approved_amount)
                if amount <= 0:
                    raise ValidationError(_('Approved amount must be greater than zero.'))
                decision = 'approved' if line.currency_id.compare_amounts(amount, line.forecast_amount) == 0 else 'adjusted'
            line.write({
                'approved_amount': amount,
                'ceo_decision': decision,
                'ceo_comment': comment or False,
                'ceo_approved_by': reviewer.id,
                'ceo_approved_date': fields.Datetime.now(),
                'state': 'approved' if decision in ('approved', 'adjusted') else 'cancel',
            })
        return True

    def action_execute(self):
        self.ensure_one()
        if self.ceo_decision not in ('approved', 'adjusted') or self.approved_amount <= 0:
            raise UserError(_('This cash planning line must be approved by the CEO before execution.'))
        if self.state == 'cancel':
            raise UserError(_('Rejected or cancelled planning lines cannot be executed.'))
        if self.payment_voucher_id or self.receipt_voucher_id or self.internal_transfer_id:
            return self.action_open_document()
        if not self.journal_id:
            raise UserError(_('Select the expected journal before execution.'))

        amount = self.approved_amount
        common = {
            'date': self.planned_date,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'description': self.description or self.name,
        }
        if self.transaction_type == 'transfer':
            if not self.destination_journal_id:
                raise UserError(_('Select a destination journal.'))
            transfer = self.env['account.internal.transfer'].create({
                **common, 'source_journal_id': self.journal_id.id,
                'line_ids': [(0, 0, {'journal_id': self.destination_journal_id.id, 'amount': amount})],
            })
            self.internal_transfer_id = transfer
            action = self._document_action('account.internal.transfer', transfer.id)
        elif self.flow_type == 'out':
            if not self.partner_id:
                raise UserError(_('Select a partner for the planned payment.'))
            voucher = self.env['account.payment.voucher'].create({
                **common, 'partner_id': self.partner_id.id, 'journal_id': self.journal_id.id,
                'account_id': self.account_id.id if self.account_id else False,
                'bill_ids': [(6, 0, self.bill_ids.ids)],
                'purchase_order_ids': [(6, 0, self.purchase_order_ids.ids)],
            })
            self.payment_voucher_id = voucher
            action = self._document_action('account.payment.voucher', voucher.id)
        else:
            if not self.partner_id:
                raise UserError(_('Select a partner for the planned receipt.'))
            if not self.account_id:
                raise UserError(_('Select an income or receivable account.'))
            voucher = self.env['account.receipt.voucher'].create({
                **common, 'partner_id': self.partner_id.id, 'journal_id': self.journal_id.id,
                'account_id': self.account_id.id, 'invoice_ids': [(6, 0, self.invoice_ids.ids)],
            })
            self.receipt_voucher_id = voucher
            action = self._document_action('account.receipt.voucher', voucher.id)
        self.state = 'executed'
        return action
