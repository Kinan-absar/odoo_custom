from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError


class PaymentVoucherSignWizard(models.TransientModel):
    _name = 'payment.voucher.sign.wizard'
    _description = 'Choose Payment Voucher Signer'

    voucher_id = fields.Many2one('account.payment.voucher', required=True, readonly=True)
    company_id = fields.Many2one(related='voucher_id.company_id')
    recipient_type = fields.Selection([('user', 'User'), ('partner', 'Contact / Partner')], default='user', required=True)
    signer_user_id = fields.Many2one('res.users', string='Signer User', domain=[('active', '=', True)])
    signer_partner_id = fields.Many2one('res.partner', string='Signer Contact')

    def action_prepare_pdf(self):
        self.ensure_one()
        if self.recipient_type == 'user':
            if not self.signer_user_id or not self.signer_user_id.active:
                raise UserError(_('Choose an active signer user.'))
            partner = self.signer_user_id.partner_id
        else:
            partner = self.signer_partner_id
        if not partner:
            raise UserError(_('Choose a signer contact.'))
        return self.voucher_id._prepare_direct_signing_pdf(partner)


class SignTemplate(models.Model):
    _inherit = 'sign.template'

    pv_voucher_id = fields.Many2one('account.payment.voucher', readonly=True, copy=False, ondelete='set null')
    pv_revision = fields.Integer(readonly=True, copy=False, default=0)
    pv_signer_partner_id = fields.Many2one('res.partner', readonly=True, copy=False)
    pv_sign_role_id = fields.Many2one('sign.item.role', readonly=True, copy=False)


class SignSendRequest(models.TransientModel):
    _inherit = 'sign.send.request'

    @api.model
    def _pv_signer_values(self, template):
        values = {'signer_ids': [Command.clear(), Command.create({
            'role_id': template.pv_sign_role_id.id, 'partner_id': template.pv_signer_partner_id.id})]}
        if 'is_user_signer' in self._fields:
            values['is_user_signer'] = False
        if 'signer_id' in self._fields:
            values['signer_id'] = template.pv_signer_partner_id.id
        return values

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        template_id = vals.get('template_id') or self.env.context.get('default_template_id')
        if not template_id and self.env.context.get('active_model') == 'sign.template':
            template_id = self.env.context.get('active_id')
        template = self.env['sign.template'].browse(template_id).exists() if template_id else False
        if template and template.pv_signer_partner_id:
            vals.update({name: value for name, value in self._pv_signer_values(template).items() if name in fields_list})
        return vals

    @api.onchange('template_id')
    def _onchange_pv_signer(self):
        for wizard in self:
            if wizard.template_id.pv_signer_partner_id:
                wizard.update(wizard._pv_signer_values(wizard.template_id))

    @api.model_create_multi
    def create(self, vals_list):
        # Choosing the current user still means sending a remote request;
        # never silently switch the voucher into the in-person Sign Now flow.
        for vals in vals_list:
            template_id = vals.get('template_id') or self.env.context.get('default_template_id')
            template = self.env['sign.template'].browse(template_id).exists() if template_id else False
            if template and template.pv_signer_partner_id and 'is_user_signer' in self._fields:
                vals['is_user_signer'] = False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('is_user_signer') and any(w.template_id.pv_signer_partner_id for w in self):
            vals = dict(vals, is_user_signer=False)
        return super().write(vals)
