# -*- coding: utf-8 -*-

from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape


class EmployeeMessageWizard(models.TransientModel):
    _name = 'employee.message.wizard'
    _description = 'Start Employee Message'

    allowed_partner_ids = fields.Many2many(
        'res.partner',
        compute='_compute_allowed_partner_ids',
        string='Allowed Recipients',
    )
    recipient_partner_id = fields.Many2one(
        'res.partner',
        string='To Employee',
        required=True,
        domain="[('id', 'in', allowed_partner_ids)]",
    )
    # Kept for upgrade compatibility with older patched versions.
    recipient_id = fields.Many2one(
        'employee.message.recipient',
        string='Legacy Recipient',
        domain="[('partner_id', '!=', False)]",
    )
    employee_id = fields.Many2one('hr.employee', string='Legacy To Employee')
    body = fields.Text(string='Message', required=True)

    @api.depends()
    def _compute_allowed_partner_ids(self):
        employees = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
            ('user_id.partner_id', '!=', False),
            ('user_id.active', '=', True),
        ])
        partner_ids = employees.mapped('user_id.partner_id').ids
        for wizard in self:
            wizard.allowed_partner_ids = [(6, 0, partner_ids)]

    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        employee_id = self.env.context.get('default_employee_id')
        partner_id = self.env.context.get('default_recipient_partner_id')
        if employee_id and not partner_id:
            employee = self.env['hr.employee'].sudo().browse(employee_id)
            if employee.exists() and employee.user_id and employee.user_id.partner_id:
                partner_id = employee.user_id.partner_id.id
        if partner_id and 'recipient_partner_id' in fields_list:
            values['recipient_partner_id'] = partner_id
        return values

    def _eps_channel_model_name(self):
        return 'discuss.channel' if 'discuss.channel' in self.env else 'mail.channel'

    def _eps_channel_partner_ids(self, channel):
        if 'channel_partner_ids' in channel._fields:
            return channel.channel_partner_ids.ids
        if 'channel_member_ids' in channel._fields:
            return channel.channel_member_ids.mapped('partner_id').ids
        return []

    def _eps_find_direct_channel(self, partner_a, partner_b):
        Channel = self.env[self._eps_channel_model_name()].sudo()
        domain = [('channel_type', '=', 'chat')]
        if 'channel_partner_ids' in Channel._fields:
            domain += [('channel_partner_ids', 'in', [partner_a.id]), ('channel_partner_ids', 'in', [partner_b.id])]
        elif 'channel_member_ids' in Channel._fields:
            domain += [('channel_member_ids.partner_id', 'in', [partner_a.id]), ('channel_member_ids.partner_id', 'in', [partner_b.id])]
        else:
            return Channel.browse()
        channels = Channel.search(domain, order='write_date desc', limit=30)
        for channel in channels:
            if {partner_a.id, partner_b.id}.issubset(set(self._eps_channel_partner_ids(channel))):
                return channel
        return Channel.browse()

    def _eps_create_direct_channel(self, partner_a, partner_b):
        Channel = self.env[self._eps_channel_model_name()].sudo()
        vals = {
            'name': '%s, %s' % (partner_a.name or _('Employee'), partner_b.name or _('Employee')),
        }
        if 'channel_type' in Channel._fields:
            vals['channel_type'] = 'chat'
        if 'channel_partner_ids' in Channel._fields:
            vals['channel_partner_ids'] = [(4, partner_a.id), (4, partner_b.id)]
        elif 'channel_member_ids' in Channel._fields:
            vals['channel_member_ids'] = [
                (0, 0, {'partner_id': partner_a.id}),
                (0, 0, {'partner_id': partner_b.id}),
            ]
        channel = Channel.create(vals)
        return channel

    def _target_partner(self):
        self.ensure_one()
        if self.recipient_partner_id:
            return self.recipient_partner_id.sudo()
        if self.recipient_id and self.recipient_id.partner_id:
            return self.recipient_id.sudo().partner_id
        raise UserError(_('Please select an employee recipient.'))

    def action_send_message(self):
        self.ensure_one()
        current_partner = self.env.user.partner_id.sudo()
        target_partner = self._target_partner()
        if not target_partner:
            raise UserError(_('The selected employee is not linked to a user account.'))
        if target_partner.id == current_partner.id:
            raise UserError(_('You cannot start a private conversation with yourself.'))

        allowed_partner_ids = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id.partner_id', '=', target_partner.id),
            ('user_id.active', '=', True),
        ], limit=1)
        if not allowed_partner_ids:
            raise UserError(_('You can only message employees linked to active user accounts.'))

        channel = self._eps_find_direct_channel(current_partner, target_partner)
        if not channel:
            channel = self._eps_create_direct_channel(current_partner, target_partner)

        clean_body = Markup('<p>%s</p>' % html_escape(self.body or '').replace('\n', '<br/>'))
        channel.message_post(
            body=clean_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=current_partner.id,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Message sent'),
                'message': _('Your message was sent to %s.') % (target_partner.name,),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
