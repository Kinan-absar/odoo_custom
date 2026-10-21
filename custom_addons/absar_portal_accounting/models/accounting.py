import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

# A process-local identity; RPC clients cannot manufacture this trusted context.
_REVIEW_TOKEN = object()
_logger = logging.getLogger(__name__)


class Company(models.Model):
    _inherit = 'res.company'

    portal_accounting_journal_ids = fields.Many2many(
        'account.journal', 'absar_portal_company_journal_rel', 'company_id', 'journal_id',
        string='Portal Accounting Journals',
        help='Only these journals are available using their accounting screen. Empty means no journal access.')
    portal_accounting_review_internal = fields.Boolean(string='Review Internal Submissions Too', default=True,
        help='Manual posting of vendor bills, miscellaneous entries and vouchers in the selected journals submits them for the same independent review. Automatic posting of bank-payment/statement entries is excluded.')

    @api.constrains('portal_accounting_journal_ids')
    def _check_portal_journals(self):
        for company in self:
            if any(j.company_id != company for j in company.portal_accounting_journal_ids):
                raise UserError(_('Portal journals must belong to this company.'))


class PortalReview(models.AbstractModel):
    _name = 'absar.accounting.review.mixin'
    _description = 'Portal accounting review metadata'

    portal_accounting_issuer_id = fields.Many2one('res.users', readonly=True, copy=False)
    portal_accounting_review = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('returned', 'Returned for Correction'), ('approved', 'Approved')],
        default='draft', readonly=True, copy=False, tracking=True)
    portal_accounting_reviewer_id = fields.Many2one('res.users', readonly=True, copy=False)
    portal_accounting_comment = fields.Text(copy=False)
    portal_accounting_review_required = fields.Boolean(readonly=True, copy=False, default=False)
    portal_accounting_reset_pending = fields.Boolean(readonly=True, copy=False)
    portal_accounting_reset_requested_by = fields.Many2one('res.users', readonly=True, copy=False)
    portal_accounting_reset_reason = fields.Text(readonly=True, copy=False)
    portal_accounting_can_review = fields.Boolean(compute='_compute_portal_accounting_can_review')

    def _portal_accounting_path(self, user):
        self.ensure_one()
        kind = {'account.payment.voucher': 'payments', 'account.receipt.voucher': 'receipts'}.get(self._name)
        if self._name == 'account.move':
            kind = {'in_invoice': 'bills', 'in_refund': 'refunds', 'entry': 'journals'}.get(self.move_type)
        if user.share:
            return '/my/employee/accounting/%s/%s?company_id=%s' % (kind, self.id, self.company_id.id)
        return '/web#id=%s&model=%s&view_type=form' % (self.id, self._name)

    def _portal_accounting_reviewers(self):
        self.ensure_one()
        group = self.env.ref('absar_portal_accounting.group_approver')
        users = self.env['res.users'].sudo().search([
            ('active', '=', True), ('company_ids', 'in', self.company_id.id),
            ('groups_id', 'in', group.id),
            ('id', 'not in', list({self.portal_accounting_issuer_id.id, self.env.uid}))])
        def eligible(user):
            if user.has_group('employee_portal_suite.group_attendance_only'):
                return False
            if user.share:
                return bool(user.with_company(self.company_id).employee_id and
                            self.journal_id in self.company_id.portal_accounting_journal_ids)
            try:
                self.with_user(user).check_access('write')
                return True
            except AccessError:
                return False
        return users.filtered(eligible)

    def _portal_accounting_notify(self, users, title, note):
        self.ensure_one()
        users = users.sudo().filtered(lambda u: u.active and self.company_id in u.company_ids)
        if not users:
            return
        # Explicit recipients: a chatter note alone does not alert approvers.
        for portal in (False, True):
            recipients = users.filtered(lambda u: bool(u.share) == portal)
            if recipients:
                self.sudo().message_post(body=Markup('<p><strong>%s</strong></p><p>%s</p><p><a href="%s">%s</a></p>') % (
                    title, note, self._portal_accounting_path(recipients[:1]), _('Open accounting document')),
                    partner_ids=recipients.partner_id.ids, message_type='comment', subtype_xmlid='mail.mt_comment',
                    author_id=self.env.user.partner_id.id,
                    email_from=self.env.user.email_formatted or self.company_id.partner_id.email_formatted or 'Accounting <noreply@localhost>')
        if 'employee.portal.webpush.service' in self.env:
            for user in users:
                try:
                    with self.env.cr.savepoint():
                        self.env['employee.portal.webpush.service'].sudo().send_to_user(
                            user, title, note, path=self._portal_accounting_path(user),
                            tag='accounting-%s-%s' % (self._name, self.id))
                except Exception:
                    _logger.warning('Optional accounting webpush failed for %s %s', self._name, self.id, exc_info=True)

    def _portal_accounting_close_review_activities(self):
        self.ensure_one()
        self.sudo().activity_ids.filtered(lambda a:
            a.summary == 'Accounting approval: %s/%s' % (self._name, self.id) and
            a.activity_type_id == self.env.ref('mail.mail_activity_data_todo')
        ).action_feedback(feedback=_('Accounting review completed or withdrawn.'))

    def _portal_accounting_notify_submission(self):
        self.ensure_one()
        reviewers = self._portal_accounting_reviewers()
        if not reviewers:
            raise UserError(_('No independent Accounting Approver with access is available for this company. Assign one before submitting.'))
        title = _('Accounting document %s awaiting approval') % (self.display_name or self.id)
        note = _('%s submitted this document for approval and posting.') % self.env.user.name
        self._portal_accounting_notify(reviewers, title, note)
        self._portal_accounting_close_review_activities()
        for reviewer in reviewers.filtered(lambda u: not u.share):
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=reviewer.id,
                summary='Accounting approval: %s/%s' % (self._name, self.id),
                note=Markup('<p>%s</p><a href="%s">%s</a>') % (note, self._portal_accounting_path(reviewer), _('Review document')))

    @api.depends_context('uid')
    @api.depends('state', 'portal_accounting_review', 'portal_accounting_issuer_id', 'portal_accounting_review_required')
    def _compute_portal_accounting_can_review(self):
        for record in self:
            record.portal_accounting_can_review = (not self.env.user.share
                and self.env.user.has_group('absar_portal_accounting.group_approver')
                and record.portal_accounting_review_required and record.state == 'draft'
                and record.portal_accounting_review == 'submitted' and record.portal_accounting_issuer_id != self.env.user)

    def _portal_native_review(self, action, confirmations=None):
        self.ensure_one()
        if self.env.user.share:
            raise AccessError(_('Use the employee accounting workspace.'))
        self.check_access('write')
        service = self.env['absar.portal.accounting.service']
        company = service._company(self.company_id.id)
        kind = {'account.payment.voucher':'payments','account.receipt.voucher':'receipts'}.get(self._name)
        if self._name == 'account.move':
            kind = {'in_invoice':'bills','in_refund':'refunds','entry':'journals'}.get(self.move_type)
        if action == 'post' and not self.portal_accounting_can_review:
            raise AccessError(_('An independent Accounting Approver is required.'))
        try:
            with self.env.cr.savepoint():
                service._act(company, kind, self.id, action, dict(confirmations or {}, version=str(self.write_date), comment=self.portal_accounting_comment or ''))
        except UserError as error:
            if action != 'post' or not str(error).startswith(('ACCOUNTING WARNING:', 'PO OVERPAYMENT:')):
                raise
            dialog = self.env['absar.accounting.post.confirm'].create({
                'kind':kind, 'record_id':self.id, 'version':str(self.write_date), 'warning':str(error),
                'confirm_abnormal':bool((confirmations or {}).get('confirm_abnormal')),
                'confirm_overpayment':bool((confirmations or {}).get('confirm_overpayment'))})
            return {'type':'ir.actions.act_window','name':_('Review Accounting Warning'),
                'res_model':dialog._name,'res_id':dialog.id,'view_mode':'form','target':'new'}
        return {'type':'ir.actions.client','tag':'reload'}

    def action_portal_accounting_approve(self):
        return self._portal_native_review('post')

    def action_portal_accounting_return(self):
        return self._portal_native_review('return')
    portal_accounting_requires_review = fields.Boolean(compute='_compute_portal_accounting_requires_review')

    @api.depends_context('uid')
    @api.depends('journal_id', 'state', 'portal_accounting_review_required', 'company_id.portal_accounting_journal_ids')
    def _compute_portal_accounting_requires_review(self):
        restricted = self.env.user.has_group('absar_portal_accounting.group_preparer')
        for record in self:
            enabled = record.state == 'draft' and (record.portal_accounting_review_required or
                restricted)
            if record._name == 'account.move':
                enabled = enabled and record.move_type in ('in_invoice','in_refund','entry') and not record.origin_payment_id and not record.statement_line_id and not ('stock_move_id' in record._fields and record.stock_move_id)
            record.portal_accounting_requires_review = bool(enabled)

    def action_portal_accounting_submit(self):
        if not self._portal_accounting_submit_native():
            raise UserError(_('This document does not require a new internal submission.'))
        return self._portal_submission_action()

    def _portal_accounting_submit_native(self):
        """Return True when an internal posting request becomes a submission.

        Existing native accounting ACLs remain responsible for internal access.
        Only manually-posted records in the explicit company journal allowlist
        join this review. Portal gateway posting already has an approved review.
        """
        pending = self.filtered(lambda r: r.state == 'draft' and r.portal_accounting_review != 'approved'
            and self.env.user.has_group('absar_portal_accounting.group_preparer'))
        if not pending or self.env.user.share or self.env.context.get('_absar_accounting_token') is _REVIEW_TOKEN:
            return False
        if len(pending) != len(self):
            raise UserError(_('Post reviewed and unreviewed documents separately. No documents were posted.'))
        self.check_access('write')
        for record in pending:
            record.sudo().write({'portal_accounting_review_required': True, 'portal_accounting_issuer_id': record.portal_accounting_issuer_id.id or self.env.uid,
                          'portal_accounting_review': 'submitted', 'portal_accounting_reviewer_id': False,
                          'portal_accounting_comment': False})
            record.message_post(body=_('Submitted for independent accounting review by %s.') % self.env.user.name,
                                subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id,
                                email_from=self.env.user.email_formatted or record.company_id.partner_id.email_formatted or 'Accounting <noreply@localhost>')
        return True

    def _portal_submission_action(self):
        return {'type':'ir.actions.client', 'tag':'display_notification', 'params':{
            'title':_('Submitted for Accounting Approval'),
            'message':_('The document remains in Draft until an independent Accounting Approver posts it using their accounting screen.'),
            'type':'success', 'sticky':True}}

    def _portal_accounting_lock(self, version):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM "' + self._table + '" WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if not version or str(self.write_date) != version:
            raise UserError(_('This record changed. Reload it before saving or acting.'))

    @api.model_create_multi
    def create(self, vals_list):
        protected = {'portal_accounting_review_required','portal_accounting_issuer_id','portal_accounting_review','portal_accounting_reviewer_id'}
        if not self.env.su and any(protected.intersection(vals) for vals in vals_list):
            raise AccessError(_('Accounting review metadata is managed by the review workflow.'))
        return super().create(vals_list)

    def write(self, vals):
        protected = {'portal_accounting_review_required','portal_accounting_issuer_id','portal_accounting_review','portal_accounting_reviewer_id'}
        if self and not self.env.su and protected.intersection(vals):
            raise AccessError(_('Accounting review metadata is managed by the review workflow.'))
        # Ordinary native edits must invalidate an existing portal review too.
        # This prevents posting content different from the submitted document.
        business = {k for k in vals if not k.startswith(('portal_accounting_', 'message_', 'activity_'))
                    and k not in ('access_token', 'access_url', 'access_warning')}
        submitted = self.filtered(lambda r: r.portal_accounting_review == 'submitted')
        if business and self.env.context.get('_absar_accounting_token') is not _REVIEW_TOKEN:
            for record in self:
                if record.state == 'draft' and record.portal_accounting_review_required and record.portal_accounting_review in ('submitted', 'approved'):
                    super(PortalReview, record).write({
                        'portal_accounting_review': 'returned',
                        'portal_accounting_reviewer_id': False,
                        'portal_accounting_comment': _('Document changed; submit it again for review.'),
                    })
        if vals.get('state') == 'draft':
            vals = dict(vals, portal_accounting_reset_pending=False)
        result = super().write(vals)
        for record in self:
            if record.portal_accounting_review == 'submitted' and record not in submitted:
                record._portal_accounting_notify_submission()
            elif record in submitted and record.portal_accounting_review != 'submitted':
                record._portal_accounting_close_review_activities()
        return result


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'absar.accounting.review.mixin']

    def write(self, vals):
        # Editing only the native review reason must not let dynamic-line
        # synchronization invalidate the submitted content being reviewed.
        if vals and set(vals) <= {'portal_accounting_comment'} and self.env.user.has_group('absar_portal_accounting.group_approver'):
            return super(AccountMove, self.with_context(_absar_accounting_token=_REVIEW_TOKEN)).write(vals)
        return super().write(vals)

    def action_post(self):
        manual = self.filtered(lambda m: m.move_type in ('in_invoice','in_refund','entry')
            and not m.origin_payment_id and not m.statement_line_id
            and not ('stock_move_id' in m._fields and m.stock_move_id))
        if manual and manual._portal_accounting_submit_native():
            if len(manual) != len(self):
                raise UserError(_('Submit vendor bills and manual entries separately from other documents.'))
            return manual._portal_submission_action()
        return super().action_post()

    def _post(self, soft=True):
        for move in self:
            if move.portal_accounting_review_required and move.portal_accounting_review != 'approved':
                raise UserError(_('This portal document requires independent accounting approval before posting.'))
        return super(AccountMove, self.with_context(_absar_accounting_token=_REVIEW_TOKEN))._post(soft=soft)


class MoveLine(models.Model):
    _inherit = 'account.move.line'

    def write(self, vals):
        moves = self.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_review_required
                                     and m.portal_accounting_review in ('submitted', 'approved'))
        if moves and self.env.context.get('_absar_accounting_token') is not _REVIEW_TOKEN:
            moves.sudo().write({'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False,
                         'portal_accounting_comment': _('Entry lines changed; submit it again for review.')})
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('_absar_accounting_token') is not _REVIEW_TOKEN:
            records.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_review_required
                and m.portal_accounting_review in ('submitted', 'approved')).sudo().write({
                    'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False})
        return records

    def unlink(self):
        if self.env.context.get('_absar_accounting_token') is not _REVIEW_TOKEN:
            self.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_review_required
                and m.portal_accounting_review in ('submitted', 'approved')).sudo().write({
                    'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False})
        return super().unlink()


class PaymentVoucher(models.Model):
    _name = 'account.payment.voucher'
    _inherit = ['account.payment.voucher', 'absar.accounting.review.mixin']

    def action_post(self):
        if self._portal_accounting_submit_native():
            return self._portal_submission_action()
        for rec in self:
            if rec.portal_accounting_review_required and rec.portal_accounting_review != 'approved':
                raise UserError(_('This portal voucher requires independent accounting approval.'))
        return super(PaymentVoucher, self.with_context(_absar_accounting_token=_REVIEW_TOKEN)).action_post()


class ReceiptVoucher(models.Model):
    _name = 'account.receipt.voucher'
    _inherit = ['account.receipt.voucher', 'absar.accounting.review.mixin']

    def action_post(self):
        if self._portal_accounting_submit_native():
            return self._portal_submission_action()
        for rec in self:
            if rec.portal_accounting_review_required and rec.portal_accounting_review != 'approved':
                raise UserError(_('This portal voucher requires independent accounting approval.'))
        return super(ReceiptVoucher, self.with_context(_absar_accounting_token=_REVIEW_TOKEN)).action_post()


class PlanLine(models.Model):
    _name = 'cash.plan.line'
    _inherit = ['cash.plan.line', 'absar.accounting.review.mixin']


def _invalidate_voucher_review(vouchers):
    if not vouchers.env.context.get('_absar_accounting_action'):
        vouchers.filtered(lambda v: v.state == 'draft' and v.portal_accounting_review_required
            and v.portal_accounting_review in ('submitted', 'approved')).sudo().write({
                'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False,
                'portal_accounting_comment': _('Voucher allocations changed; submit again for review.')})


class VoucherDestination(models.Model):
    _inherit = 'account.payment.voucher.line'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _invalidate_voucher_review(records.voucher_id)
        return records

    def write(self, vals):
        _invalidate_voucher_review(self.voucher_id)
        return super().write(vals)

    def unlink(self):
        _invalidate_voucher_review(self.voucher_id)
        return super().unlink()


class VoucherAllocation(models.Model):
    _inherit = 'account.payment.voucher.po.allocation'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _invalidate_voucher_review(records.voucher_id)
        return records

    def write(self, vals):
        _invalidate_voucher_review(self.voucher_id)
        return super().write(vals)

    def unlink(self):
        _invalidate_voucher_review(self.voucher_id)
        return super().unlink()
