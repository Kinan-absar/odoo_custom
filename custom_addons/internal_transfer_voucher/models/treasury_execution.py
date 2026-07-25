from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CashPlanLineExecution(models.Model):
    _inherit = 'cash.plan.line'

    is_unplanned_actual = fields.Boolean(string='Unplanned Actual', default=False, readonly=True, copy=False, index=True)
    actual_source = fields.Selection([
        ('planned', 'Planned Payment'),
        ('direct_voucher', 'Direct Payment Voucher'),
    ], string='Actual Source', default='planned', readonly=True, copy=False)

    def _is_execution_manager(self):
        return self.env.user.has_group('internal_transfer_voucher.group_payment_execution_manager')

    def _locked_business_fields(self):
        return {
            'run_id', 'planned_date', 'flow_type', 'transaction_type', 'category_id',
            'name', 'partner_id', 'project_id', 'forecast_amount', 'priority',
            'funding_status', 'journal_id', 'destination_journal_id', 'account_id',
            'purchase_order_ids', 'bill_ids', 'invoice_ids', 'description',
        }

    def write(self, vals):
        if not self.env.context.get('cash_plan_workflow_write'):
            protected = self._locked_business_fields().intersection(vals)
            for line in self:
                if protected and line.flow_type == 'out' and line.ceo_decision != 'not_sent':
                    raise UserError(_(
                        'This planned payment is locked after submission to the CEO. '
                        'Reset it to Draft before changing payment details.'
                    ))
                if line.is_unplanned_actual and protected:
                    raise UserError(_('Unplanned actual lines are controlled by their Payment Voucher.'))
        return super().write(vals)

    def action_mark_as_paid_create_voucher(self):
        self.ensure_one()
        if not self._is_execution_manager():
            raise UserError(_('Only Payment Execution Managers can execute an approved payment.'))
        if self.flow_type != 'out' or self.ceo_decision not in ('approved', 'adjusted'):
            raise UserError(_('Only CEO-approved planned payments can be executed.'))
        if self.payment_voucher_id:
            return self.action_open_document()
        if not self.journal_id:
            raise UserError(_('Select the payment journal before marking this payment as paid.'))
        if not self.partner_id:
            raise UserError(_('Select the payment partner.'))

        amount = self.approved_amount
        voucher = self.env['account.payment.voucher'].with_context(skip_unplanned_actual_sync=True).create({
            'date': self.planned_date,
            'amount': amount,
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'account_id': self.account_id.id if self.account_id else False,
            'description': self.description or self.name,
            'bill_ids': [(6, 0, self.bill_ids.ids)],
            'purchase_order_ids': [(6, 0, self.purchase_order_ids.ids)],
            'cash_plan_line_id': self.id,
        })
        self.with_context(cash_plan_workflow_write=True).write({
            'payment_voucher_id': voucher.id,
            'state': 'paid',
        })
        self.activity_ids.filtered(
            lambda a: a.summary == _('Execute approved payment') and a.user_id == self.env.user
        ).action_done()
        return self._document_action('account.payment.voucher', voucher.id)


class AccountPaymentVoucherCashPlan(models.Model):
    _inherit = 'account.payment.voucher'

    cash_plan_line_id = fields.Many2one('cash.plan.line', string='Weekly Plan Line', readonly=True, copy=False, index=True)

    def _matching_weekly_run(self):
        self.ensure_one()
        return self.env['cash.plan.run'].search([
            ('company_id', '=', self.company_id.id),
            ('date_from', '<=', self.date),
            ('date_to', '>=', self.date),
            ('state', '!=', 'cancel'),
        ], order='date_from desc, id desc', limit=1)

    def _unplanned_category(self):
        self.ensure_one()
        category = self.env['cash.plan.category'].search([
            ('company_id', 'in', [False, self.company_id.id]),
            ('flow_type', '=', 'out'),
            ('name', '=', 'Unplanned Actual Payments'),
        ], limit=1)
        if not category:
            category = self.env['cash.plan.category'].sudo().create({
                'name': 'Unplanned Actual Payments',
                'flow_type': 'out',
                'company_id': self.company_id.id,
                'sequence': 999,
            })
        return category

    def _sync_unplanned_actual(self):
        for voucher in self:
            if voucher.cash_plan_line_id or voucher.state == 'cancel' or not voucher.date:
                continue
            run = voucher._matching_weekly_run()
            if not run:
                continue
            line = self.env['cash.plan.line'].with_context(cash_plan_workflow_write=True).create({
                'run_id': run.id,
                'planned_date': voucher.date,
                'flow_type': 'out',
                'transaction_type': 'supplier' if voucher.partner_id.supplier_rank else 'other',
                'category_id': voucher._unplanned_category().id,
                'name': _('Unplanned Actual - %s') % voucher.name,
                'partner_id': voucher.partner_id.id,
                'forecast_amount': 0.0,
                'journal_id': voucher.journal_id.id,
                'account_id': voucher.account_id.id if voucher.account_id else False,
                'purchase_order_ids': [(6, 0, voucher.purchase_order_ids.ids)],
                'payment_voucher_id': voucher.id,
                'state': 'paid',
                'ceo_decision': 'not_required',
                'approved_amount': 0.0,
                'is_unplanned_actual': True,
                'actual_source': 'direct_voucher',
            })
            line.with_context(cash_plan_workflow_write=True).write({'ceo_decision': 'not_required', 'state': 'paid'})
            voucher.with_context(skip_unplanned_actual_sync=True).write({'cash_plan_line_id': line.id})

    def action_post(self):
        result = super().action_post()
        self._sync_unplanned_actual()
        return result

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_unplanned_actual_sync'):
            for voucher in self.filtered('cash_plan_line_id'):
                line = voucher.cash_plan_line_id
                if line.is_unplanned_actual:
                    run = voucher._matching_weekly_run()
                    update = {
                        'planned_date': voucher.date,
                        'partner_id': voucher.partner_id.id,
                        'journal_id': voucher.journal_id.id,
                        'account_id': voucher.account_id.id if voucher.account_id else False,
                        'purchase_order_ids': [(6, 0, voucher.purchase_order_ids.ids)],
                    }
                    if run:
                        update['run_id'] = run.id
                    line.with_context(cash_plan_workflow_write=True).write(update)
        return result
