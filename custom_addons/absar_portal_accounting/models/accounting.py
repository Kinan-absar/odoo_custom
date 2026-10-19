from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class Company(models.Model):
    _inherit = 'res.company'

    portal_accounting_journal_ids = fields.Many2many(
        'account.journal', 'absar_portal_company_journal_rel', 'company_id', 'journal_id',
        string='Portal Accounting Journals',
        help='Only these journals are available in the accounting workspace. Empty means no journal access.')
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
    portal_accounting_comment = fields.Text(readonly=True, copy=False)
    portal_accounting_requires_review = fields.Boolean(compute='_compute_portal_accounting_requires_review')

    @api.depends('journal_id', 'state', 'company_id.portal_accounting_review_internal', 'company_id.portal_accounting_journal_ids')
    def _compute_portal_accounting_requires_review(self):
        for record in self:
            enabled = record.state == 'draft' and record.company_id.portal_accounting_review_internal and record.journal_id in record.company_id.portal_accounting_journal_ids
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
            and r.company_id.portal_accounting_review_internal
            and r.journal_id in r.company_id.portal_accounting_journal_ids)
        if not pending or self.env.user.share or self.env.context.get('_absar_accounting_action'):
            return False
        if len(pending) != len(self):
            raise UserError(_('Post reviewed and unreviewed documents separately. No documents were posted.'))
        self.check_access('write')
        for record in pending:
            record.write({'portal_accounting_issuer_id': record.portal_accounting_issuer_id.id or self.env.uid,
                          'portal_accounting_review': 'submitted', 'portal_accounting_reviewer_id': False,
                          'portal_accounting_comment': False})
            record.message_post(body=_('Submitted for independent accounting review by %s.') % self.env.user.name,
                                subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id,
                                email_from=self.env.user.email_formatted or record.company_id.partner_id.email_formatted or 'Accounting <noreply@localhost>')
        return True

    def _portal_submission_action(self):
        return {'type':'ir.actions.client', 'tag':'display_notification', 'params':{
            'title':_('Submitted for Accounting Approval'),
            'message':_('The document remains in Draft until an independent Accounting Approver posts it in the accounting workspace.'),
            'type':'success', 'sticky':True}}

    def _portal_accounting_lock(self, version):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM "' + self._table + '" WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if not version or str(self.write_date) != version:
            raise UserError(_('This record changed. Reload it before saving or acting.'))

    def write(self, vals):
        # Ordinary native edits must invalidate an existing portal review too.
        # This prevents posting content different from the submitted document.
        business = {k for k in vals if not k.startswith(('portal_accounting_', 'message_', 'activity_'))
                    and k not in ('access_token', 'access_url', 'access_warning')}
        if business and not self.env.context.get('_absar_accounting_action'):
            for record in self:
                if record.state == 'draft' and record.portal_accounting_issuer_id and record.portal_accounting_review in ('submitted', 'approved'):
                    super(PortalReview, record).write({
                        'portal_accounting_review': 'returned',
                        'portal_accounting_reviewer_id': False,
                        'portal_accounting_comment': _('Document changed; submit it again for review.'),
                    })
        return super().write(vals)


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'absar.accounting.review.mixin']

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
            if move.portal_accounting_issuer_id and move.portal_accounting_review != 'approved':
                raise UserError(_('This portal document requires independent accounting approval before posting.'))
        return super(AccountMove, self.with_context(_absar_accounting_action=True))._post(soft=soft)


class MoveLine(models.Model):
    _inherit = 'account.move.line'

    def write(self, vals):
        moves = self.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_issuer_id
                                     and m.portal_accounting_review in ('submitted', 'approved'))
        if moves and not self.env.context.get('_absar_accounting_action'):
            moves.write({'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False,
                         'portal_accounting_comment': _('Entry lines changed; submit it again for review.')})
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('_absar_accounting_action'):
            records.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_issuer_id
                and m.portal_accounting_review in ('submitted', 'approved')).write({
                    'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False})
        return records

    def unlink(self):
        if not self.env.context.get('_absar_accounting_action'):
            self.move_id.filtered(lambda m: m.state == 'draft' and m.portal_accounting_issuer_id
                and m.portal_accounting_review in ('submitted', 'approved')).write({
                    'portal_accounting_review': 'returned', 'portal_accounting_reviewer_id': False})
        return super().unlink()


class PaymentVoucher(models.Model):
    _name = 'account.payment.voucher'
    _inherit = ['account.payment.voucher', 'absar.accounting.review.mixin']

    def action_post(self):
        if self._portal_accounting_submit_native():
            return self._portal_submission_action()
        for rec in self:
            if rec.portal_accounting_issuer_id and rec.portal_accounting_review != 'approved':
                raise UserError(_('This portal voucher requires independent accounting approval.'))
        return super(PaymentVoucher, self.with_context(_absar_accounting_action=True)).action_post()


class ReceiptVoucher(models.Model):
    _name = 'account.receipt.voucher'
    _inherit = ['account.receipt.voucher', 'absar.accounting.review.mixin']

    def action_post(self):
        if self._portal_accounting_submit_native():
            return self._portal_submission_action()
        for rec in self:
            if rec.portal_accounting_issuer_id and rec.portal_accounting_review != 'approved':
                raise UserError(_('This portal voucher requires independent accounting approval.'))
        return super(ReceiptVoucher, self.with_context(_absar_accounting_action=True)).action_post()


class PlanLine(models.Model):
    _name = 'cash.plan.line'
    _inherit = ['cash.plan.line', 'absar.accounting.review.mixin']


def _invalidate_voucher_review(vouchers):
    if not vouchers.env.context.get('_absar_accounting_action'):
        vouchers.filtered(lambda v: v.state == 'draft' and v.portal_accounting_issuer_id
            and v.portal_accounting_review in ('submitted', 'approved')).write({
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
