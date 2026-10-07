from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PaymentVoucher(models.Model):
    _inherit = 'account.payment.voucher'

    project_id = fields.Many2one('project.project', string='Signing Project', tracking=True,
                                 help='Select the project whose signing workflow should be used; otherwise the company default applies.')
    sign_template_id = fields.Many2one('sign.template', readonly=True, copy=False)
    sign_request_id = fields.Many2one('sign.request', readonly=True, copy=False)
    signing_workflow_id = fields.Many2one('absar.sign.workflow', readonly=True, copy=False)
    signature_state = fields.Selection([
        ('draft', 'Not Sent'), ('pending', 'Signing in Progress'),
        ('signed', 'Fully Signed'), ('rejected', 'Rejected'),
    ], default='draft', copy=False, tracking=True)
    signature_status_text = fields.Char(default='Not Sent', readonly=True, copy=False)
    signature_completed_count = fields.Integer(readonly=True, copy=False)
    signature_total_count = fields.Integer(readonly=True, copy=False)
    revision = fields.Integer(default=0, copy=False, tracking=True)

    @api.constrains('project_id', 'company_id')
    def _check_signing_project_company(self):
        for rec in self:
            if rec.project_id.company_id and rec.project_id.company_id != rec.company_id:
                raise ValidationError(_('The signing project must belong to the voucher company.'))

    def action_send_to_sign(self):
        self.ensure_one()
        if self.state not in ('draft', 'posted'):
            raise UserError(_('A cancelled Payment Voucher cannot be sent to Sign.'))
        if self.signature_state != 'draft':
            raise UserError(_('This voucher is already prepared for signing. Open Signature Status.'))
        if not self.partner_id or not self.journal_id:
            raise UserError(_('Set the supplier and journal before sending to Sign.'))
        amount = sum(self.line_ids.mapped('amount')) if self.payment_method == 'journal_transfer' else self.amount
        if amount <= 0:
            raise UserError(_('The Payment Voucher amount must be greater than zero before signing.'))
        template, workflow, status = self.env['absar.sign.workflow.service'].create_template(
            self, 'internal_transfer_voucher.action_payment_voucher_pdf', _('Payment Voucher'),
            [self.name, self.partner_id.name, self.project_id.name],
        )
        self.with_context(skip_payment_voucher_sign_reset=True).write({
            'sign_template_id': template.id, 'signing_workflow_id': workflow.id,
            'signature_state': 'pending', 'signature_status_text': status,
            'signature_completed_count': 0, 'signature_total_count': len(workflow.step_ids),
        })
        self.message_post(body=_('Payment Voucher prepared for signing with workflow: %s') % workflow.name)
        return {'type': 'ir.actions.act_url', 'url': f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}', 'target': 'self'}

    def action_open_signature_status(self):
        return self.env['absar.sign.workflow.service'].open_status(self)

    def _reset_voucher_signature(self):
        for rec in self.filtered(lambda voucher: voucher.sign_template_id):
            rec.with_context(skip_payment_voucher_sign_reset=True).write({
                'revision': rec.revision + 1, 'signature_state': 'draft',
                'signature_status_text': _('Not Sent'), 'sign_template_id': False,
                'sign_request_id': False, 'signing_workflow_id': False,
                'signature_completed_count': 0, 'signature_total_count': 0,
            })
            rec.message_post(body=_('Voucher content changed. Previous signing PDF retained as history; revision R%s requires new signatures.') % rec.revision)

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_payment_voucher_sign_reset'):
            printed_fields = {
                'date', 'partner_id', 'amount', 'currency_id', 'company_id', 'journal_id',
                'account_id', 'payment_method', 'description', 'project_id', 'state',
                'line_ids', 'purchase_order_ids', 'purchase_order_id', 'po_allocation_ids',
                'bill_ids', 'cheque_number', 'cheque_date', 'bank_transfer_ref',
                'has_bank_fees', 'fee_amount', 'fee_account_id', 'fee_tax_id', 'analytic_distribution',
            }
            if printed_fields.intersection(vals):
                self._reset_voucher_signature()
        return result

    @api.model
    def _cron_sync_voucher_sign_status(self):
        service = self.env['absar.sign.workflow.service']
        for rec in self.search([('sign_template_id', '!=', False), ('signature_state', '=', 'pending')]):
            service.sync_record(rec, 'skip_payment_voucher_sign_reset')


class PaymentVoucherLine(models.Model):
    _inherit = 'account.payment.voucher.line'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.mapped('voucher_id')._reset_voucher_signature()
        return records

    def write(self, vals):
        vouchers = self.mapped('voucher_id')
        result = super().write(vals)
        (vouchers | self.mapped('voucher_id'))._reset_voucher_signature()
        return result

    def unlink(self):
        vouchers = self.mapped('voucher_id')
        result = super().unlink()
        vouchers._reset_voucher_signature()
        return result
