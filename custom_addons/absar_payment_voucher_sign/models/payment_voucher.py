import base64
import re
import io

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

from odoo.addons.absar_sign_workflow_core.tools.signature_anchors import locate_signature_anchors

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PaymentVoucher(models.Model):
    _inherit = 'account.payment.voucher'

    # Legacy fields retained for upgrade/history; unused by direct signing.
    project_id = fields.Many2one('project.project', string='Signing Project', readonly=True)
    signing_workflow_id = fields.Many2one('absar.sign.workflow', readonly=True, copy=False)
    sign_template_id = fields.Many2one('sign.template', compute='_compute_sign_template', store=False)
    sign_request_id = fields.Many2one('sign.request', compute='_compute_signature_status', store=False)
    signature_state = fields.Selection([
        ('draft', 'Not Sent'), ('prepared', 'Prepared — Not Sent'),
        ('pending', 'Signing in Progress'), ('signed', 'Fully Signed'), ('rejected', 'Rejected'),
    ], compute='_compute_signature_status', store=False, tracking=False)
    signature_status_text = fields.Char(compute='_compute_signature_status', store=False)
    signature_completed_count = fields.Integer(compute='_compute_signature_status', store=False)
    signature_total_count = fields.Integer(compute='_compute_signature_status', store=False)
    revision = fields.Integer(default=0, copy=False, tracking=True)

    @api.depends('revision')
    def _compute_sign_template(self):
        for rec in self:
            rec.sign_template_id = self.env['sign.template'].search([
                ('pv_voucher_id', '=', rec._origin.id), ('pv_revision', '=', rec.revision),
            ], order='id desc', limit=1) if rec._origin.id else self.env['sign.template']

    @api.depends('sign_template_id', 'revision')
    def _compute_signature_status(self):
        # Read Sign progress without writing to a posted voucher.
        for rec in self:
            request = self.env['sign.request'].search(
                [('template_id', '=', rec.sign_template_id.id)], order='id desc', limit=1,
            ) if rec.sign_template_id else self.env['sign.request']
            rec.sign_request_id = request
            rec.signature_completed_count = 0
            rec.signature_total_count = 0
            if not rec.sign_template_id:
                rec.signature_state = 'draft'
                rec.signature_status_text = _('Not Sent')
            elif not request:
                rec.signature_state = 'prepared'
                rec.signature_total_count = len(rec.sign_template_id.sign_item_ids.mapped('responsible_id'))
                rec.signature_status_text = _('PDF Ready — Awaiting Send')
            else:
                items = self.env['sign.request.item'].search([('sign_request_id', '=', request.id)])
                completed = items.filtered(lambda item: (
                    ('state' in item._fields and item.state in ('completed', 'signed'))
                    or any(name in item._fields and bool(item[name]) for name in ('is_signed', 'signed', 'completed'))
                ))
                rec.signature_total_count = len(items)
                rec.signature_completed_count = len(completed)
                if request.state == 'signed':
                    rec.signature_state = 'signed'
                    rec.signature_completed_count = len(items)
                    rec.signature_status_text = _('Fully Signed')
                elif request.state in ('canceled', 'refused'):
                    rec.signature_state = 'rejected'
                    rec.signature_status_text = _('Cancelled / Rejected')
                else:
                    rec.signature_state = 'pending'
                    rec.signature_status_text = _('%s/%s Signed') % (len(completed), len(items))

    def _check_can_prepare_signature(self):
        self.ensure_one()
        self.check_access_rights('write')
        self.check_access_rule('write')
        if self.state != 'posted':
            raise UserError(_('Post the Payment Voucher before preparing it for signing.'))
        if self.sign_template_id:
            raise UserError(_('This voucher already has a signing PDF. Open Signature Status.'))
        if not self.partner_id or not self.journal_id:
            raise UserError(_('Set the supplier and journal before preparing the signing PDF.'))
        amount = sum(self.line_ids.mapped('amount')) if self.payment_method == 'journal_transfer' else self.amount
        if amount <= 0:
            raise UserError(_('The Payment Voucher amount must be greater than zero before signing.'))

    def action_send_to_sign(self):
        self._check_can_prepare_signature()
        return {'type': 'ir.actions.act_window', 'name': _('Choose Voucher Signer'),
                'res_model': 'payment.voucher.sign.wizard', 'view_mode': 'form', 'target': 'new',
                'context': dict(self.env.context, default_voucher_id=self.id)}

    def _prepare_direct_signing_pdf(self, partner, signing_as="received", paid_partner=False):
        # Recheck after opening the picker in case the voucher was reset or
        # cancelled. Serialize preparation to avoid duplicate PDFs.
        self._check_can_prepare_signature()
        self.env.cr.execute('SELECT id FROM account_payment_voucher WHERE id = %s FOR UPDATE', (self.id,))
        self.invalidate_recordset(['state', 'revision', 'sign_template_id'])
        self._check_can_prepare_signature()
        if signing_as not in ('paid', 'received', 'both'):
            raise UserError(_('Choose Paid By, Received By, or both.'))
        recipients = [('received', partner)] if signing_as == 'received' else [('paid', partner)]
        if signing_as == 'both':
            if not paid_partner:
                raise UserError(_('Choose the Paid By signer.'))
            recipients = [('paid', paid_partner), ('received', partner)]
        for _slot, contact in recipients:
            contact.ensure_one()
            contact.check_access_rights('read')
            contact.check_access_rule('read')
            if not contact.email:
                raise UserError(_('Set an email address on every selected signer contact before continuing.'))
            if contact.company_id and contact.company_id != self.company_id:
                raise UserError(_('Every signer contact must be shared or belong to the voucher company.'))
        pdf, _format = self.env['ir.actions.report']._render_qweb_pdf(
            'internal_transfer_voucher.action_payment_voucher_pdf', self.ids)
        filename = '%s - %s' % (self.name, self.partner_id.name)
        if self.revision:
            filename += '_R%s' % self.revision
        attachment = self.env['ir.attachment'].create({
            'name': filename + '.pdf', 'datas': base64.b64encode(pdf), 'type': 'binary',
            'mimetype': 'application/pdf', 'res_model': self._name, 'res_id': self.id})
        Role = self.env['sign.item.role'].sudo()
        roles = {}
        for slot, contact in recipients:
            label = 'Paid By' if slot == 'paid' else 'Received By'
            role = Role.search([('name', '=', label)], limit=1)
            if not role:
                role = Role.create({'name': label})
            roles[slot] = role
        primary_slot = 'received' if signing_as in ('received', 'both') else 'paid'
        template_values = {
            'name': _('Payment Voucher - %s') % filename, 'attachment_id': attachment.id,
            'pv_voucher_id': self.id, 'pv_revision': self.revision,
            'pv_signer_partner_id': partner.id, 'pv_sign_role_id': roles[primary_slot].id,
        }
        for slot, contact in recipients:
            template_values['pv_%s_partner_id' % slot] = contact.id
            template_values['pv_%s_role_id' % slot] = roles[slot].id
        template = self.env['sign.template'].create(template_values)
        page_count = len(PdfReader(io.BytesIO(pdf)).pages)
        issues = []
        for slot, contact in recipients:
            label = 'Paid By' if slot == 'paid' else 'Received By'
            try:
                anchor = locate_signature_anchors(
                    pdf, page_count, {slot: label}, prefer_signature_area=True,
                )[slot]
            except (ValueError, ImportError) as exc:
                issues.append('%s: %s' % (label, exc))
                anchor = {'page': page_count, 'posX': 0.04 if slot == 'paid' else 0.65, 'posY': 0.80}
            for xmlid, item_label, offset, width, height in [
                ('sign.sign_item_type_signature', _('Signature'), 0, 0.26, 0.031),
                ('sign.sign_item_type_date', _('Date'), 0.038, 0.155, 0.015),
            ]:
                item_type = self.env.ref(xmlid, raise_if_not_found=False)
                if not item_type:
                    raise UserError(_('Odoo Sign field type is missing: %s') % item_label)
                self.env['sign.item'].sudo().create({
                    'template_id': template.id, 'type_id': item_type.id, 'required': True,
                    'responsible_id': roles[slot].id, 'page': anchor['page'],
                    'posX': anchor['posX'], 'posY': anchor['posY'] + offset,
                    'width': width, 'height': height, 'name': '%s - %s' % (label, item_label)})
        # All signing data lives on Sign records. Never write to the posted
        # voucher, and never bypass its financial write restriction.
        self.invalidate_recordset(['sign_template_id', 'sign_request_id', 'signature_state',
                                   'signature_status_text', 'signature_completed_count', 'signature_total_count'])
        action = {'type': 'ir.actions.act_url',
                  'url': '/odoo/sign/%s/action-sign.Template?id=%s' % (template.id, template.id), 'target': 'self'}
        if issues:
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'title': _('Review voucher signature positions · Not sent'),
                'message': ' '.join(issues) + ' ' + _('Adjust fields before using Send.'),
                'type': 'warning', 'sticky': True, 'next': action,
            }}
        return action

    def action_open_signature_status(self):
        self.ensure_one()
        if self.sign_request_id:
            return {'type': 'ir.actions.act_window', 'name': _('Signature Request'),
                    'res_model': 'sign.request', 'res_id': self.sign_request_id.id,
                    'view_mode': 'form', 'target': 'current'}
        if self.sign_template_id:
            return {'type': 'ir.actions.act_url',
                    'url': '/odoo/sign/%s/action-sign.Template?id=%s' % (self.sign_template_id.id, self.sign_template_id.id), 'target': 'self'}
        raise UserError(_('This voucher has no signing PDF.'))

    def _reset_voucher_signature(self):
        for rec in self.filtered(lambda voucher: voucher.state == 'draft' and voucher.sign_template_id):
            rec.with_context(skip_payment_voucher_sign_reset=True).write({
                'revision': rec.revision + 1})
            rec.message_post(body=_('Voucher content changed. Previous signing PDF retained as history; revision R%s requires new signatures.') % rec.revision)

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get('skip_payment_voucher_sign_reset'):
            printed_fields = {
                'date', 'partner_id', 'amount', 'currency_id', 'company_id', 'journal_id',
                'account_id', 'payment_method', 'description', 'line_ids',
                'purchase_order_ids', 'purchase_order_id', 'po_allocation_ids', 'bill_ids',
                'cheque_number', 'cheque_date', 'bank_transfer_ref', 'has_bank_fees',
                'fee_amount', 'fee_account_id', 'fee_tax_id', 'analytic_distribution',
            }
            # Posting alone changes no printed content: retain signed PDF and
            # never follow it with writes to the locked posted voucher.
            if printed_fields.intersection(vals):
                self._reset_voucher_signature()
        return result

    @api.model
    def _cron_sync_voucher_sign_status(self):
        # Legacy noupdate cron: status is now computed, with no voucher writes.
        return True

    @api.model
    def _migrate_to_direct_signing(self):
        # Preserve old PDFs/requests but stop legacy workflow callbacks from
        # writing progress to posted vouchers. No voucher content is changed.
        templates = self.env['sign.template'].sudo().search([
            ('absar_source_model', '=', 'account.payment.voucher')])
        for template in templates:
            voucher = self.sudo().browse(template.absar_source_id).exists()
            template.write({'pv_voucher_id': voucher.id if voucher else False,
                            'absar_source_model': False, 'absar_source_id': False,
                            'absar_workflow_id': False})
        # Import revision metadata from both earlier signing implementations.
        # Do not make an old R0 PDF current for a voucher already edited to R1.
        for template in self.env['sign.template'].sudo().search([('pv_voucher_id', '!=', False)]):
            match = re.search(r'_R(\d+)\.pdf$', template.attachment_id.name or '', re.IGNORECASE)
            template.pv_revision = int(match.group(1)) if match else 0
        cron = self.env.ref('absar_payment_voucher_sign.cron_sync_payment_voucher_sign', raise_if_not_found=False)
        if cron:
            cron.sudo().write({'active': False})
        builtin = self.env.ref('absar_payment_voucher_sign.template_payment_voucher_director_ceo', raise_if_not_found=False)
        if builtin:
            builtin.sudo().unlink()
        return True


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
