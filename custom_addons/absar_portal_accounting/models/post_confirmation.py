from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class AccountingPostConfirmation(models.TransientModel):
    _name = 'absar.accounting.post.confirm'
    _description = 'Native accounting posting warning confirmation'

    kind = fields.Selection([('bills','Vendor Bill'),('refunds','Vendor Credit Note'),('journals','Journal Entry'),('payments','Payment Voucher'),('receipts','Receipt Voucher')], required=True, readonly=True)
    record_id = fields.Integer(required=True, readonly=True)
    version = fields.Char(required=True, readonly=True)
    warning = fields.Text(readonly=True)
    confirm_abnormal = fields.Boolean(string='I reviewed and acknowledge the accounting warning')
    confirm_overpayment = fields.Boolean(string='I explicitly confirm the PO overpayment shown above')

    @api.model_create_multi
    def create(self, values):
        if self.env.user.share or not self.env.user.has_group('absar_portal_accounting.group_approver'):
            raise AccessError(_('Use the appropriate accounting interface for this account.'))
        return super().create(values)

    def action_confirm(self):
        self.ensure_one()
        if self.env.user.share or not self.env.user.has_group('absar_portal_accounting.group_approver'):
            raise AccessError(_('An internal Accounting Approver is required.'))
        models_by_kind = {'bills':'account.move','refunds':'account.move','journals':'account.move','payments':'account.payment.voucher','receipts':'account.receipt.voucher'}
        record = self.env[models_by_kind[self.kind]].browse(self.record_id).exists()
        if not record:
            raise UserError(_('The document is no longer available.'))
        record.check_access('write')
        record._portal_accounting_lock(self.version)
        return record._portal_native_review('post', {'confirm_abnormal':self.confirm_abnormal,'confirm_overpayment':self.confirm_overpayment})
