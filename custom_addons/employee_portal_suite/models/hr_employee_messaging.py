# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

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
        channels = Channel.search(domain, order='write_date desc', limit=20)
        for channel in channels:
            members = set(self._eps_channel_partner_ids(channel))
            if {partner_a.id, partner_b.id}.issubset(members):
                return channel
        return Channel.browse()

    def _eps_create_direct_channel(self, partner_a, partner_b):
        Channel = self.env[self._eps_channel_model_name()].sudo()
        vals = {'name': '%s, %s' % (partner_a.name or _('Employee'), partner_b.name or _('Employee'))}
        if 'channel_type' in Channel._fields:
            vals['channel_type'] = 'chat'
        if 'channel_partner_ids' in Channel._fields:
            vals['channel_partner_ids'] = [(4, partner_a.id), (4, partner_b.id)]
        elif 'channel_member_ids' in Channel._fields:
            vals['channel_member_ids'] = [(0, 0, {'partner_id': partner_a.id}), (0, 0, {'partner_id': partner_b.id})]
        return Channel.create(vals)

    def action_open_employee_portal_message(self):
        self.ensure_one()
        current_partner = self.env.user.partner_id
        target_partner = self.user_id.partner_id if self.user_id else False
        if not target_partner:
            raise UserError(_('This employee is not linked to a user account, so they cannot receive messages.'))
        if target_partner == current_partner:
            raise UserError(_('You cannot start a private conversation with yourself.'))
        channel = self._eps_find_direct_channel(current_partner.sudo(), target_partner.sudo())
        if not channel:
            channel = self._eps_create_direct_channel(current_partner.sudo(), target_partner.sudo())
        return {
            'type': 'ir.actions.act_url',
            'url': '/my/employee/messages/%s' % channel.id,
            'target': 'self',
        }
