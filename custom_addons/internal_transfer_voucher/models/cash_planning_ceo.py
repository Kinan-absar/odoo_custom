from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from markupsafe import Markup, escape


class CashPlanRunCEO(models.Model):
    _inherit = 'cash.plan.run'

    # Kept for compatibility with plans created by previous versions. Approval is now line-level only.
    ceo_reviewed_by = fields.Many2one('res.users', string='CEO Reviewed By', readonly=True, copy=False, tracking=True)
    ceo_reviewed_date = fields.Datetime(string='CEO Reviewed On', readonly=True, copy=False, tracking=True)
    ceo_comment = fields.Text(string='CEO Plan Comment', tracking=True)
    ceo_status = fields.Selection([
        ('not_sent', 'Not Sent'),
        ('pending', 'Pending Payment Reviews'),
        ('approved', 'Payments Reviewed'),
        ('rejected', 'Contains Rejected Payments'),
    ], string='CEO Review Status', default='not_sent', required=True, tracking=True, copy=False,
       compute='_compute_ceo_summary', store=True)
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
        'line_ids.ceo_decision', 'line_ids.approved_amount', 'line_ids.state'
    )
    def _compute_ceo_summary(self):
        for run in self:
            active = run.line_ids.filtered(lambda line: line.state != 'cancel' or line.ceo_decision == 'rejected')
            payments = active.filtered(lambda line: line.flow_type == 'out')
            receipts = active.filtered(lambda line: line.flow_type == 'in')
            pending = payments.filtered(lambda line: line.ceo_decision == 'pending')
            approved = payments.filtered(lambda line: line.ceo_decision in ('approved', 'adjusted'))
            rejected = payments.filtered(lambda line: line.ceo_decision == 'rejected')
            held = payments.filtered(lambda line: line.ceo_decision == 'held')

            run.ceo_pending_count = len(pending)
            run.ceo_approved_count = len(approved)
            run.ceo_rejected_count = len(rejected)
            run.ceo_held_count = len(held)
            # Receipts are forecasts only and never require CEO approval.
            run.approved_inflow = sum(receipts.mapped('forecast_amount'))
            run.approved_outflow = sum(approved.mapped('approved_amount'))
            run.approved_net = run.approved_inflow - run.approved_outflow
            run.approved_closing = run.opening_balance + run.approved_net
            if pending or held:
                run.ceo_status = 'pending'
            elif rejected:
                run.ceo_status = 'rejected'
            elif approved:
                run.ceo_status = 'approved'
            else:
                run.ceo_status = 'not_sent'

    # Weekly plans are planning containers only; they are not CEO approval documents.
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
        ('rejected', 'Rejected'),
        ('held', 'On Hold'),
        ('not_required', 'No Approval Required'),
    ], default='not_sent', required=True, tracking=True, copy=False)
    ceo_comment = fields.Text(string='CEO Comment', tracking=True, copy=False)
    ceo_approved_by = fields.Many2one('res.users', string='CEO Reviewed By', readonly=True, copy=False)
    ceo_approved_date = fields.Datetime(string='CEO Reviewed On', readonly=True, copy=False)
    execution_amount = fields.Monetary(string='Execution Amount', compute='_compute_execution_amount', store=True)
    run_state = fields.Selection(related='run_id.state', string='Weekly Plan Status', readonly=True)
    run_ceo_status = fields.Selection(related='run_id.ceo_status', string='Weekly CEO Status', readonly=True)
    marked_paid_by = fields.Many2one('res.users', string='Marked Paid By', readonly=True, copy=False, tracking=True)
    marked_paid_date = fields.Datetime(string='Marked Paid On', readonly=True, copy=False, tracking=True)

    def init(self):
        # Repair data created by the earlier weekly-plan approval workflow.
        self.env.cr.execute("""
            UPDATE cash_plan_line
               SET ceo_decision = 'not_required',
                   approved_amount = forecast_amount
             WHERE flow_type = 'in'
               AND COALESCE(ceo_decision, '') != 'not_required'
        """)
        self.env.cr.execute("""
            UPDATE cash_plan_line
               SET state = 'planned',
                   ceo_decision = 'not_sent',
                   approved_amount = 0,
                   ceo_approved_by = NULL,
                   ceo_approved_date = NULL
             WHERE flow_type = 'out'
               AND state = 'cancel'
               AND COALESCE(ceo_decision, '') = 'pending'
        """)
        self.env.cr.execute("""
            UPDATE cash_plan_line
               SET state = 'awaiting_payment'
             WHERE flow_type = 'out'
               AND state = 'approved'
               AND ceo_decision IN ('approved', 'adjusted')
               AND payment_voucher_id IS NULL
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
            if record.flow_type == 'in':
                record.write({'ceo_decision': 'not_required', 'approved_amount': record.forecast_amount})
            else:
                record.write({'ceo_decision': 'not_sent', 'approved_amount': 0.0})
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'flow_type' in vals or 'forecast_amount' in vals:
            for line in self:
                if line.flow_type == 'in' and (
                    line.ceo_decision != 'not_required' or
                    line.currency_id.compare_amounts(line.approved_amount, line.forecast_amount) != 0
                ):
                    super(CashPlanLineCEO, line).write({
                        'ceo_decision': 'not_required',
                        'approved_amount': line.forecast_amount,
                        'ceo_comment': False,
                        'ceo_approved_by': False,
                        'ceo_approved_date': False,
                    })
                elif line.flow_type == 'out' and line.ceo_decision == 'not_required':
                    super(CashPlanLineCEO, line).write({
                        'ceo_decision': 'not_sent',
                        'approved_amount': 0.0,
                    })
        return result

    def action_submit_to_ceo(self):
        for line in self:
            if line.flow_type != 'out':
                raise UserError(_('Receipts do not require CEO approval.'))
            if line.state == 'executed':
                raise UserError(_('An executed payment cannot be resubmitted.'))
            if not line.partner_id:
                raise UserError(_('Select the supplier before submitting this planned payment to the CEO.'))
            line.write({
                'state': 'planned',
                'ceo_decision': 'pending',
                'approved_amount': 0.0,
                'ceo_comment': False,
                'ceo_approved_by': False,
                'ceo_approved_date': False,
            })
        return True

    def action_reset_to_draft(self):
        for line in self:
            if line.state == 'executed':
                raise UserError(_('An executed movement cannot be reset to draft.'))
            values = {'state': 'planned', 'ceo_comment': False, 'ceo_approved_by': False, 'ceo_approved_date': False}
            if line.flow_type == 'out':
                values.update({'ceo_decision': 'not_sent', 'approved_amount': 0.0})
            else:
                values.update({'ceo_decision': 'not_required', 'approved_amount': line.forecast_amount})
            line.write(values)
        return True

    def action_approve(self):
        raise UserError(_('Planned payments must be approved by the CEO from the Employee Portal.'))

    def _weekly_plan_notification_users(self):
        self.ensure_one()
        group = self.env.ref(
            'internal_transfer_voucher.group_weekly_payment_plan_manager',
            raise_if_not_found=False,
        )
        if not group:
            return self.env['res.users']
        return group.sudo().users.filtered(
            lambda user: user.active
            and not user.share
            and self.company_id in user.company_ids
        )

    def _payment_execution_users(self):
        self.ensure_one()
        group = self.env.ref(
            'internal_transfer_voucher.group_payment_execution_manager',
            raise_if_not_found=False,
        )
        if not group:
            return self.env['res.users']
        return group.sudo().users.filtered(
            lambda user: user.active
            and not user.share
            and self.company_id in user.company_ids
        )

    def _notify_execution_managers(self, reviewer):
        self.ensure_one()
        users = self._payment_execution_users()
        if not users:
            return
        backend_url = '/web#id=%s&model=cash.plan.line&view_type=form' % self.id
        body = Markup(
            '<strong>%s</strong><br/>%s <strong>%s</strong>.<br/><a href="%s">%s</a>'
        ) % (
            escape(_('Payment ready for execution')),
            escape(_('The CEO approved planned payment')),
            escape(self.display_name),
            escape(backend_url),
            escape(_('Open Planned Payment')),
        )
        self.sudo().message_post(
            body=body,
            partner_ids=users.mapped('partner_id').ids,
            subtype_xmlid='mail.mt_comment',
            author_id=reviewer.partner_id.id,
        )
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        existing_users = self.sudo().activity_ids.filtered(
            lambda activity: activity.activity_type_id == activity_type
            and activity.user_id in users
            and activity.summary == _('Mark approved payment as paid')
        ).mapped('user_id')
        for user in users - existing_users:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_('Mark approved payment as paid'),
                note=Markup('%s<br/><a href="%s">%s</a>') % (
                    escape(_('The CEO approved this payment. Confirm it as paid, then create the Payment Voucher.')),
                    escape(backend_url),
                    escape(_('Open Planned Payment')),
                ),
            )

    def _notify_weekly_plan_group(self, decision, reviewer):
        self.ensure_one()
        users = self._weekly_plan_notification_users()
        if not users:
            return

        decision_labels = {
            'approved': _('approved'),
            'adjusted': _('approved with an adjusted amount'),
            'rejected': _('rejected'),
            'held': _('placed on hold'),
        }
        decision_label = decision_labels.get(decision, decision)
        backend_url = '/web#id=%s&model=cash.plan.line&view_type=form' % self.id
        amount_text = ('%s %.2f' % (self.currency_id.symbol or self.currency_id.name, self.approved_amount)) if decision in ('approved', 'adjusted') else ''
        amount_line = Markup('<br/><strong>%s:</strong> %s') % (
            escape(_('Approved Amount')),
            escape(amount_text),
        ) if amount_text else Markup('')
        comment_line = Markup('<br/><strong>%s:</strong> %s') % (
            escape(_('CEO Comment')),
            escape(self.ceo_comment),
        ) if self.ceo_comment else Markup('')

        body = Markup(
            '<strong>%s</strong><br/>'
            '%s <strong>%s</strong> %s %s.'
            '%s%s<br/>'
            '<a href="%s">%s</a>'
        ) % (
            escape(_('CEO Payment Decision')),
            escape(_('Planned payment')),
            escape(self.display_name),
            escape(_('was')),
            escape(decision_label),
            amount_line,
            comment_line,
            escape(backend_url),
            escape(_('Open Planned Payment')),
        )

        self.sudo().message_post(
            body=body,
            partner_ids=users.mapped('partner_id').ids,
            subtype_xmlid='mail.mt_comment',
            author_id=reviewer.partner_id.id,
        )

        if decision in ('approved', 'adjusted'):
            existing_users = self.sudo().activity_ids.filtered(
                lambda activity: activity.activity_type_id == self.env.ref('mail.mail_activity_data_todo')
                and activity.user_id in users
                and activity.summary == _('Execute approved payment')
            ).mapped('user_id')
            for user in users - existing_users:
                self.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Execute approved payment'),
                    note=Markup('%s<br/><a href="%s">%s</a>') % (
                        escape(_('The CEO approved this planned payment. Please proceed with execution.')),
                        escape(backend_url),
                        escape(_('Open Planned Payment')),
                    ),
                )

    def action_ceo_decide(self, decision, approved_amount=None, comment=None, reviewer=None):
        if decision not in ('approved', 'adjusted', 'rejected', 'held'):
            raise ValidationError(_('Invalid CEO decision.'))
        reviewer = reviewer or self.env.user
        for line in self:
            if line.flow_type != 'out':
                raise UserError(_('Receipts do not require CEO approval.'))
            if line.ceo_decision not in ('pending', 'held'):
                raise UserError(_('Only payments pending CEO review or currently on hold can be reviewed.'))
            amount = 0.0
            final_decision = decision
            if decision not in ('rejected', 'held'):
                amount = line.forecast_amount if approved_amount is None else float(approved_amount)
                if amount <= 0:
                    raise ValidationError(_('Approved amount must be greater than zero.'))
                final_decision = 'approved' if line.currency_id.compare_amounts(amount, line.forecast_amount) == 0 else 'adjusted'
            line.write({
                'approved_amount': amount,
                'ceo_decision': final_decision,
                'ceo_comment': comment or False,
                'ceo_approved_by': reviewer.id,
                'ceo_approved_date': fields.Datetime.now(),
                'state': ('awaiting_payment' if final_decision in ('approved', 'adjusted') else
                          'planned' if final_decision == 'held' else 'cancel'),
                'marked_paid_by': False,
                'marked_paid_date': False,
            })
            line._notify_weekly_plan_group(final_decision, reviewer)
            if final_decision in ('approved', 'adjusted'):
                line._notify_execution_managers(reviewer)
        return True

    def action_mark_as_paid(self):
        if not self.env.user.has_group('internal_transfer_voucher.group_payment_execution_manager'):
            raise UserError(_('Only Payment Execution Managers can mark an approved payment as paid.'))
        for line in self:
            if line.flow_type != 'out':
                raise UserError(_('Only planned payments can be marked as paid.'))
            if line.ceo_decision not in ('approved', 'adjusted') or line.state != 'awaiting_payment':
                raise UserError(_('The payment must be approved by the CEO and awaiting payment.'))
            line.write({
                'state': 'marked_paid',
                'marked_paid_by': self.env.user.id,
                'marked_paid_date': fields.Datetime.now(),
            })
            activity_type = self.env.ref('mail.mail_activity_data_todo')
            line.sudo().activity_ids.filtered(
                lambda activity: activity.activity_type_id == activity_type
                and activity.user_id == self.env.user
                and activity.summary == _('Mark approved payment as paid')
            ).action_done()

            users = line._payment_execution_users()
            backend_url = '/web#id=%s&model=cash.plan.line&view_type=form' % line.id
            line.sudo().message_post(
                body=Markup('<strong>%s</strong><br/>%s<br/><a href="%s">%s</a>') % (
                    escape(_('Payment marked as paid')),
                    escape(_('Create the Payment Voucher to complete the payment record.')),
                    escape(backend_url),
                    escape(_('Open Planned Payment')),
                ),
                partner_ids=users.mapped('partner_id').ids,
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.user.partner_id.id,
            )
            existing_users = line.sudo().activity_ids.filtered(
                lambda activity: activity.activity_type_id == activity_type
                and activity.user_id in users
                and activity.summary == _('Create Payment Voucher')
            ).mapped('user_id')
            for user in users - existing_users:
                line.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Create Payment Voucher'),
                    note=Markup('%s<br/><a href="%s">%s</a>') % (
                        escape(_('The payment was marked as paid. Create its Payment Voucher.')),
                        escape(backend_url),
                        escape(_('Open Planned Payment')),
                    ),
                )
        return True

    def action_execute(self):
        self.ensure_one()
        if self.flow_type == 'out':
            if not self.env.user.has_group('internal_transfer_voucher.group_payment_execution_manager'):
                raise UserError(_('Only Payment Execution Managers can create the Payment Voucher.'))
            if self.ceo_decision not in ('approved', 'adjusted') or self.approved_amount <= 0:
                raise UserError(_('This planned payment must be approved by the CEO before execution.'))
            if self.state != 'marked_paid':
                raise UserError(_('Mark the approved payment as paid before creating its Payment Voucher.'))
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
                'planned_cash_line_id': self.id,
                'cash_plan_run_id': self.run_id.id,
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
