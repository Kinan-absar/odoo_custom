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
    payment_marked_by = fields.Many2one('res.users', string='Marked as Paid By', readonly=True, copy=False)
    payment_marked_date = fields.Datetime(string='Marked as Paid On', readonly=True, copy=False)
    run_state = fields.Selection(related='run_id.state', string='Weekly Plan Status', readonly=True)
    run_ceo_status = fields.Selection(related='run_id.ceo_status', string='Weekly CEO Status', readonly=True)

    # A reset approval is intentionally one-time.  Each new reset request must be
    # approved again by a Payment Execution Manager.
    reset_request_pending = fields.Boolean(
        string='Reset to Draft Requested', default=False, readonly=True, copy=False, tracking=True
    )
    reset_requested_by = fields.Many2one(
        'res.users', string='Reset Requested By', readonly=True, copy=False, tracking=True
    )
    reset_requested_on = fields.Datetime(
        string='Reset Requested On', readonly=True, copy=False, tracking=True
    )
    reset_approved_by = fields.Many2one(
        'res.users', string='Reset Approved By', readonly=True, copy=False, tracking=True
    )
    reset_approved_on = fields.Datetime(
        string='Reset Approved On', readonly=True, copy=False, tracking=True
    )

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
            if record.is_unplanned:
                # Unplanned Actuals are raised directly by the Accountant and never go
                # through the CEO approval flow.
                continue
            if record.flow_type == 'in':
                record.write({'ceo_decision': 'not_required', 'approved_amount': record.forecast_amount})
            else:
                record.write({'ceo_decision': 'not_sent', 'approved_amount': 0.0})
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'flow_type' in vals or 'forecast_amount' in vals:
            for line in self:
                if line.is_unplanned:
                    continue
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
        """Reset directly for Execution Managers; otherwise request one-time approval."""
        for line in self:
            if line.state == 'executed':
                raise UserError(_('An executed movement cannot be reset to draft.'))

            is_execution_manager = self.env.user.has_group(
                'internal_transfer_voucher.group_payment_execution_manager'
            )
            if is_execution_manager:
                now = fields.Datetime.now()
                values = {
                    'state': 'planned',
                    'ceo_comment': False,
                    'ceo_approved_by': False,
                    'ceo_approved_date': False,
                    'reset_request_pending': False,
                    'reset_approved_by': self.env.user.id,
                    'reset_approved_on': now,
                }
                if line.flow_type == 'out':
                    values.update({'ceo_decision': 'not_sent', 'approved_amount': 0.0})
                else:
                    values.update({'ceo_decision': 'not_required', 'approved_amount': line.forecast_amount})
                line.with_context(allow_locked_write=True).write(values)

                # If somebody had already requested this reset, close all related
                # approval activities when the Execution Manager performs it.
                todo = self.env.ref('mail.mail_activity_data_todo')
                activities = line.sudo().activity_ids.filtered(
                    lambda activity: activity.activity_type_id == todo
                    and activity.summary == _('Approve Reset to Draft')
                )
                if activities:
                    activities.action_feedback(feedback=_('Reset to draft completed.'))

                line.sudo().message_post(
                    body=Markup('<strong>%s</strong><br/>%s') % (
                        escape(_('Reset to Draft')),
                        escape(_('The planned payment was reset to draft by %s.') % self.env.user.display_name),
                    ),
                    subtype_xmlid='mail.mt_comment',
                    author_id=self.env.user.partner_id.id,
                )
                continue

            line._check_group(
                'internal_transfer_voucher.group_weekly_payment_plan_manager',
                'Only a Weekly Payment Plan Manager can request a reset to draft.',
            )
            if line.reset_request_pending:
                raise UserError(_('A reset to draft request is already waiting for approval.'))

            users = line._group_users('internal_transfer_voucher.group_payment_execution_manager')
            if not users:
                raise UserError(_('No Payment Execution Manager is available for this company.'))

            now = fields.Datetime.now()
            line.with_context(allow_locked_write=True).write({
                'reset_request_pending': True,
                'reset_requested_by': self.env.user.id,
                'reset_requested_on': now,
                'reset_approved_by': False,
                'reset_approved_on': False,
            })

            backend_url = '/web#id=%s&model=cash.plan.line&view_type=form' % line.id
            body = Markup(
                '<strong>%s</strong><br/>%s <strong>%s</strong>.<br/><a href="%s">%s</a>'
            ) % (
                escape(_('Reset to Draft Requested')),
                escape(_('A Weekly Payment Plan Manager requested a reset to draft for planned payment')),
                escape(line.display_name),
                escape(backend_url),
                escape(_('Open Planned Payment')),
            )
            line.sudo().message_post(
                body=body,
                partner_ids=users.mapped('partner_id').ids,
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.user.partner_id.id,
            )

            for user in users:
                line.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Approve Reset to Draft'),
                    note=Markup('%s<br/><a href="%s">%s</a>') % (
                        escape(_('A reset to draft was requested. Review the planned payment and approve the reset.')),
                        escape(backend_url),
                        escape(_('Open Planned Payment')),
                    ),
                )
        return True

    def action_approve_reset_to_draft(self):
        """Approve the current request, reset the payment, and close its activities."""
        for line in self:
            line._check_group(
                'internal_transfer_voucher.group_payment_execution_manager',
                'Only a Payment Execution Manager can approve a reset to draft.',
            )
            if not line.reset_request_pending:
                raise UserError(_('There is no pending reset to draft request.'))
            if line.state == 'executed':
                raise UserError(_('An executed movement cannot be reset to draft.'))

            now = fields.Datetime.now()
            values = {
                'state': 'planned',
                'ceo_comment': False,
                'ceo_approved_by': False,
                'ceo_approved_date': False,
                'reset_request_pending': False,
                'reset_approved_by': self.env.user.id,
                'reset_approved_on': now,
            }
            if line.flow_type == 'out':
                values.update({'ceo_decision': 'not_sent', 'approved_amount': 0.0})
            else:
                values.update({'ceo_decision': 'not_required', 'approved_amount': line.forecast_amount})
            line.with_context(allow_locked_write=True).write(values)

            # Completing the approval also completes every activity generated by
            # this reset request, so no stale notification remains for other
            # Payment Execution Managers.
            todo = self.env.ref('mail.mail_activity_data_todo')
            activities = line.sudo().activity_ids.filtered(
                lambda activity: activity.activity_type_id == todo
                and activity.summary == _('Approve Reset to Draft')
            )
            if activities:
                activities.action_feedback(feedback=_('Reset to draft approved and completed.'))

            line.sudo().message_post(
                body=Markup('<strong>%s</strong><br/>%s') % (
                    escape(_('Reset to Draft Approved')),
                    escape(_('The planned payment was reset to draft by %s.') % self.env.user.display_name),
                ),
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.user.partner_id.id,
            )
        return True

    def action_approve(self):
        """Allow Payment Execution Managers to approve a pending planned payment."""
        for line in self:
            line._check_group(
                'internal_transfer_voucher.group_payment_execution_manager',
                'Only the CEO or a Payment Execution Manager can approve this planned payment.',
            )
            line.action_ceo_decide(
                'approved',
                approved_amount=line.forecast_amount,
                reviewer=self.env.user,
            )
        return True

    def _weekly_plan_notification_users(self):
        """CEO decisions go only to Payment Execution Managers.

        Weekly Payment Plan Managers receive their separate handoff only after
        the payment is marked as paid, when the draft voucher must be created.
        """
        self.ensure_one()
        return self._group_users(
            'internal_transfer_voucher.group_payment_execution_manager',
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
            if decision in ('approved', 'adjusted') and not line.run_id:
                raise UserError(_(
                    'This planned payment must be added to a weekly plan before it can be approved.'
                ))
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
                'state': ('approved' if final_decision in ('approved', 'adjusted') else
                          'planned' if final_decision == 'held' else 'cancel'),
            })
            line._notify_weekly_plan_group(final_decision, reviewer)
        return True

    def _check_group(self, xmlid, error_message):
        self.ensure_one()
        if self.env.su:
            return
        if not self.env.user.has_group(xmlid):
            raise UserError(_(error_message))

    def _group_users(self, xmlid, exclude_xmlids=None):
        self.ensure_one()
        group = self.env.ref(xmlid, raise_if_not_found=False)
        if not group:
            return self.env['res.users']
        users = group.sudo().users.filtered(
            lambda user: user.active and not user.share and self.company_id in user.company_ids
        )
        for exclude_xmlid in (exclude_xmlids or []):
            excluded_group = self.env.ref(exclude_xmlid, raise_if_not_found=False)
            if excluded_group:
                users -= excluded_group.sudo().users
        return users

    def _check_any_group(self, xmlids, error_message):
        self.ensure_one()
        if self.env.su:
            return
        if not any(self.env.user.has_group(xmlid) for xmlid in xmlids):
            raise UserError(_(error_message))

    def action_mark_as_paid(self):
        """Payment Execution Managers confirm that the bank/cash execution is complete.

        This step does not create the accounting Payment Voucher. It hands the item to
        Weekly Payment Plan Managers, who receive a notification and create the voucher.
        """
        self.ensure_one()
        self._check_group(
            'internal_transfer_voucher.group_payment_execution_manager',
            'Only a Payment Execution Manager can mark this payment as paid.',
        )
        if self.flow_type != 'out':
            raise UserError(_('Only planned payments can be marked as paid.'))
        if self.ceo_decision not in ('approved', 'adjusted') or self.approved_amount <= 0:
            raise UserError(_('This planned payment must be approved by the CEO before it can be marked as paid.'))
        if self.state == 'cancel':
            raise UserError(_('Cancelled planned payments cannot be marked as paid.'))
        if self.state == 'executed':
            return True

        self.write({
            'state': 'executed',
            'payment_marked_by': self.env.user.id,
            'payment_marked_date': fields.Datetime.now(),
        })

        # Completing the execution step must also close the original execution
        # activity/notification created after CEO approval. Otherwise the item
        # continues to appear as pending even though it has been marked paid.
        self.sudo().activity_ids.filtered(
            lambda activity: activity.summary == _('Execute approved payment')
        ).action_done()

        users = self._group_users(
            'internal_transfer_voucher.group_weekly_payment_plan_manager',
            exclude_xmlids=['internal_transfer_voucher.group_payment_execution_manager'],
        )
        if users:
            backend_url = '/web#id=%s&model=cash.plan.line&view_type=form' % self.id
            body = Markup(
                '<strong>%s</strong><br/>%s <strong>%s</strong> %s.<br/>'
                '<a href="%s">%s</a>'
            ) % (
                escape(_('Payment Marked as Paid')),
                escape(_('The Payment Execution Manager marked planned payment')),
                escape(self.display_name),
                escape(_('as paid. Please create the Payment Voucher.')),
                escape(backend_url),
                escape(_('Open Planned Payment')),
            )
            self.sudo().message_post(
                body=body,
                partner_ids=users.mapped('partner_id').ids,
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.user.partner_id.id,
            )
            todo = self.env.ref('mail.mail_activity_data_todo')
            existing_users = self.sudo().activity_ids.filtered(
                lambda activity: activity.activity_type_id == todo
                and activity.user_id in users
                and activity.summary == _('Create Payment Voucher')
            ).mapped('user_id')
            for user in users - existing_users:
                self.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Create Payment Voucher'),
                    note=Markup('%s<br/><a href="%s">%s</a>') % (
                        escape(_('This planned payment was marked as paid. Create its draft Payment Voucher.')),
                        escape(backend_url),
                        escape(_('Open Planned Payment')),
                    ),
                )
        return True

    def action_create_payment_voucher(self):
        """Execution or Weekly Payment Plan Managers create the draft accounting voucher."""
        self.ensure_one()
        self._check_any_group(
            [
                'internal_transfer_voucher.group_weekly_payment_plan_manager',
                'internal_transfer_voucher.group_payment_execution_manager',
            ],
            'Only a Weekly Payment Plan Manager or Payment Execution Manager can create the Payment Voucher from this planned payment.',
        )
        if self.flow_type != 'out':
            raise UserError(_('This action is only available for planned payments.'))
        if self.state != 'executed':
            raise UserError(_('The Payment Execution Manager must mark this payment as paid first.'))
        if self.payment_voucher_id:
            return self.action_open_document()
        if not self.partner_id:
            raise UserError(_('Select a partner for the planned payment.'))
        if not self.journal_id:
            raise UserError(_('Select the payment journal before creating the Payment Voucher.'))

        amount = self.approved_amount
        voucher = self.env['account.payment.voucher'].with_context(skip_cash_plan_autolink=True).create({
            'date': self.planned_date or fields.Date.context_today(self),
            'amount': amount,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'description': self.description or self.name,
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'account_id': self.account_id.id if self.account_id else False,
            'bill_ids': [(6, 0, self.bill_ids.ids)],
            'purchase_order_ids': [(6, 0, self.purchase_order_ids.ids)],
        })
        self.payment_voucher_id = voucher
        voucher.cash_plan_line_id = self.id

        # Create the voucher only. Posting remains a separate accountant action
        # from the Payment Voucher form, so the new voucher stays in Draft.
        action = self._document_action('account.payment.voucher', voucher.id)

        self.sudo().activity_ids.filtered(
            lambda activity: activity.summary == _('Create Payment Voucher')
        ).action_done()
        return action

    def action_execute(self):
        """Keep the original execution action for receipts/transfers only.

        Planned outbound payments now use the explicit two-step handoff:
        Mark as Paid -> Create Payment Voucher.
        """
        self.ensure_one()
        if self.flow_type == 'out':
            raise UserError(_(
                'Use Mark as Paid first (Payment Execution Managers), then Create Payment Voucher '
                '(Weekly Payment Plan Managers).'
            ))
        return super().action_execute()

