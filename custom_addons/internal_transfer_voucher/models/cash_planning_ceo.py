from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class CashPlanRunCEO(models.Model):
    _inherit = 'cash.plan.run'

    # Compatibility/read-only summary fields. CEO approval is performed only on outgoing lines.
    ceo_reviewed_by = fields.Many2one(
        'res.users', string='Last CEO Reviewer', compute='_compute_ceo_summary', store=True, readonly=True
    )
    ceo_reviewed_date = fields.Datetime(
        string='Last CEO Review Date', compute='_compute_ceo_summary', store=True, readonly=True
    )
    ceo_comment = fields.Text(string='CEO Plan Comment', readonly=True)
    ceo_status = fields.Selection([
        ('not_sent', 'No Payments Submitted'),
        ('pending', 'Pending Payment Reviews'),
        ('approved', 'Payments Reviewed'),
        ('rejected', 'Contains Rejected Payments'),
    ], string='CEO Review Status', compute='_compute_ceo_summary', store=True, readonly=True)
    ceo_pending_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    ceo_approved_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    ceo_rejected_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    ceo_held_count = fields.Integer(compute='_compute_ceo_summary', store=True)
    approved_inflow = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_outflow = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_net = fields.Monetary(compute='_compute_ceo_summary', store=True)
    approved_closing = fields.Monetary(compute='_compute_ceo_summary', store=True)

    @api.depends(
        'opening_balance', 'line_ids.flow_type', 'line_ids.forecast_amount',
        'line_ids.ceo_decision', 'line_ids.approved_amount', 'line_ids.state',
        'line_ids.ceo_approved_by', 'line_ids.ceo_approved_date'
    )
    def _compute_ceo_summary(self):
        for run in self:
            lines = run.line_ids.filtered(lambda line: line.state != 'cancel' or line.ceo_decision == 'rejected')
            payments = lines.filtered(lambda line: line.flow_type == 'out')
            receipts = lines.filtered(lambda line: line.flow_type == 'in')
            pending = payments.filtered(lambda line: line.ceo_decision == 'pending')
            approved = payments.filtered(lambda line: line.ceo_decision in ('approved', 'adjusted'))
            rejected = payments.filtered(lambda line: line.ceo_decision == 'rejected')
            held = payments.filtered(lambda line: line.ceo_decision == 'held')

            run.ceo_pending_count = len(pending)
            run.ceo_approved_count = len(approved)
            run.ceo_rejected_count = len(rejected)
            run.ceo_held_count = len(held)
            run.approved_inflow = sum(receipts.mapped('forecast_amount'))
            run.approved_outflow = sum(approved.mapped('approved_amount'))
            run.approved_net = run.approved_inflow - run.approved_outflow
            run.approved_closing = run.opening_balance + run.approved_net

            reviewed = payments.filtered('ceo_approved_date').sorted('ceo_approved_date', reverse=True)[:1]
            run.ceo_reviewed_by = reviewed.ceo_approved_by if reviewed else False
            run.ceo_reviewed_date = reviewed.ceo_approved_date if reviewed else False

            if pending or held:
                run.ceo_status = 'pending'
            elif rejected:
                run.ceo_status = 'rejected'
            elif approved:
                run.ceo_status = 'approved'
            else:
                run.ceo_status = 'not_sent'

    # Weekly plans are forecast containers only, not CEO approval documents.
    def action_submit(self):
        return self.action_start()

    def action_approve(self):
        return self.action_start()


class CashPlanLineCEO(models.Model):
    _inherit = 'cash.plan.line'

    approved_amount = fields.Monetary(string='CEO Approved Amount', tracking=True, copy=False)
    ceo_decision = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('pending', 'Pending CEO Review'),
        ('approved', 'Approved'),
        ('adjusted', 'Approved with Adjustment'),
        ('held', 'On Hold'),
        ('rejected', 'Rejected'),
        ('not_required', 'No Approval Required'),
    ], default='not_sent', required=True, tracking=True, copy=False, index=True)
    ceo_comment = fields.Text(string='CEO Comment', tracking=True, copy=False)
    ceo_approved_by = fields.Many2one('res.users', string='CEO Reviewed By', readonly=True, copy=False)
    ceo_approved_date = fields.Datetime(string='CEO Reviewed On', readonly=True, copy=False)

    # Compatibility aliases for old portal templates still cached in ir.ui.view.
    ceo_reviewed_by = fields.Many2one(related='ceo_approved_by', string='CEO Reviewed By', readonly=True)
    ceo_reviewed_date = fields.Datetime(related='ceo_approved_date', string='CEO Reviewed On', readonly=True)

    execution_amount = fields.Monetary(string='Execution Amount', compute='_compute_execution_amount', store=True)
    run_state = fields.Selection(related='run_id.state', string='Weekly Plan Status', readonly=True)
    run_ceo_status = fields.Selection(related='run_id.ceo_status', string='Weekly CEO Status', readonly=True)

    def init(self):
        """Normalize data left by previous workflow versions without deleting records."""
        self.env.cr.execute("""
            UPDATE cash_plan_line
               SET ceo_decision = 'not_required',
                   approved_amount = forecast_amount
             WHERE flow_type = 'in'
               AND COALESCE(ceo_decision, '') <> 'not_required'
        """)
        self.env.cr.execute("""
            UPDATE cash_plan_line
               SET ceo_decision = 'not_sent',
                   approved_amount = 0
             WHERE flow_type = 'out'
               AND COALESCE(ceo_decision, '') NOT IN
                   ('not_sent','pending','approved','adjusted','held','rejected')
        """)

    @api.depends('flow_type', 'forecast_amount', 'approved_amount', 'ceo_decision')
    def _compute_execution_amount(self):
        for line in self:
            if line.flow_type == 'in':
                line.execution_amount = line.forecast_amount
            elif line.ceo_decision in ('approved', 'adjusted'):
                line.execution_amount = line.approved_amount
            else:
                line.execution_amount = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._sync_approval_defaults()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'flow_type', 'forecast_amount'} & set(vals):
            self._sync_approval_defaults()
        return result

    def _sync_approval_defaults(self):
        for line in self:
            if line.flow_type == 'in':
                values = {}
                if line.ceo_decision != 'not_required':
                    values['ceo_decision'] = 'not_required'
                if line.currency_id.compare_amounts(line.approved_amount, line.forecast_amount) != 0:
                    values['approved_amount'] = line.forecast_amount
                if values:
                    super(CashPlanLineCEO, line).write(values)
            elif line.ceo_decision == 'not_required':
                super(CashPlanLineCEO, line).write({
                    'ceo_decision': 'not_sent',
                    'approved_amount': 0.0,
                    'ceo_comment': False,
                    'ceo_approved_by': False,
                    'ceo_approved_date': False,
                })

    def action_submit_to_ceo(self):
        for line in self:
            if line.flow_type != 'out':
                raise UserError(_('Receipts do not require CEO approval.'))
            if line.state == 'executed':
                raise UserError(_('An executed payment cannot be resubmitted.'))
            line.write({
                'state': 'planned',
                'ceo_decision': 'pending',
                'approved_amount': line.forecast_amount,
                'ceo_comment': False,
                'ceo_approved_by': False,
                'ceo_approved_date': False,
            })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_reset_to_draft(self):
        for line in self:
            if line.state == 'executed':
                raise UserError(_('An executed movement cannot be reset to draft.'))
            if line.flow_type == 'out':
                line.write({
                    'state': 'planned',
                    'ceo_decision': 'not_sent',
                    'approved_amount': 0.0,
                    'ceo_comment': False,
                    'ceo_approved_by': False,
                    'ceo_approved_date': False,
                })
            else:
                line.write({
                    'state': 'planned',
                    'ceo_decision': 'not_required',
                    'approved_amount': line.forecast_amount,
                })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_approve(self):
        raise UserError(_('Planned payments must be approved by the CEO from the Employee Portal.'))

    def action_ceo_decide(self, decision, approved_amount=None, comment=None, reviewer=None):
        if decision not in ('approved', 'rejected', 'held'):
            raise ValidationError(_('Invalid CEO decision.'))
        reviewer = reviewer or self.env.user
        for line in self:
            if line.flow_type != 'out':
                raise UserError(_('Receipts do not require CEO approval.'))
            if line.ceo_decision not in ('pending', 'held'):
                raise UserError(_('Only pending or held payments can be reviewed.'))

            amount = 0.0
            final_decision = decision
            next_state = 'planned'
            if decision == 'approved':
                amount = line.forecast_amount if approved_amount is None else float(approved_amount)
                if amount <= 0:
                    raise ValidationError(_('Approved amount must be greater than zero.'))
                final_decision = (
                    'approved'
                    if line.currency_id.compare_amounts(amount, line.forecast_amount) == 0
                    else 'adjusted'
                )
                next_state = 'approved'
            elif decision == 'rejected':
                next_state = 'cancel'

            line.write({
                'approved_amount': amount,
                'ceo_decision': final_decision,
                'ceo_comment': comment or False,
                'ceo_approved_by': reviewer.id,
                'ceo_approved_date': fields.Datetime.now(),
                'state': next_state,
            })
        return True

    def action_execute(self):
        self.ensure_one()
        if self.flow_type == 'out':
            if self.ceo_decision not in ('approved', 'adjusted') or self.approved_amount <= 0:
                raise UserError(_('This planned payment must be approved by the CEO before execution.'))
            amount = self.approved_amount
        else:
            amount = self.forecast_amount

        if self.state == 'cancel':
            raise UserError(_('Cancelled planning lines cannot be executed.'))
        if self.payment_voucher_id or self.receipt_voucher_id or self.internal_transfer_id:
            return self.action_open_document()
        if not self.journal_id:
            raise UserError(_('Select the expected journal before execution.'))

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
                **common,
                'source_journal_id': self.journal_id.id,
                'line_ids': [(0, 0, {'journal_id': self.destination_journal_id.id, 'amount': amount})],
            })
            self.internal_transfer_id = transfer
            action = self._document_action('account.internal.transfer', transfer.id)
        elif self.flow_type == 'out':
            if not self.partner_id:
                raise UserError(_('Select a partner for the planned payment.'))
            voucher = self.env['account.payment.voucher'].create({
                **common,
                'partner_id': self.partner_id.id,
                'journal_id': self.journal_id.id,
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
                **common,
                'partner_id': self.partner_id.id,
                'journal_id': self.journal_id.id,
                'account_id': self.account_id.id,
                'invoice_ids': [(6, 0, self.invoice_ids.ids)],
            })
            self.receipt_voucher_id = voucher
            action = self._document_action('account.receipt.voucher', voucher.id)
        self.state = 'executed'
        return action
