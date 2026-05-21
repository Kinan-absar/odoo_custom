# -*- coding: utf-8 -*-

import json
from markupsafe import Markup
from odoo import fields, http
from odoo.http import request
from odoo.tools import html_escape
from odoo.addons.portal.controllers.portal import CustomerPortal


class EmployeePortalMessages(CustomerPortal):
    """Portal-facing employee-to-employee private messaging.

    Messaging identities are restricted to active hr.employee records that have a
    linked user account. Conversation storage uses Odoo Discuss/mail channels
    where available, so internal users can still receive messages in the normal
    Odoo communication stack.
    """

    def _channel_model_name(self):
        if 'discuss.channel' in request.env:
            return 'discuss.channel'
        return 'mail.channel'

    def _channel_model(self):
        return request.env[self._channel_model_name()].sudo()

    def _my_employee(self):
        user = request.env.user
        employee = getattr(user, 'employee_id', False)
        if employee:
            return employee.sudo()
        return request.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)

    def _messageable_employees(self):
        return request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
            ('user_id.partner_id', '!=', False),
        ], order='name asc')

    def _employee_for_partner(self, partner_id):
        return request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
            ('user_id.partner_id', '=', int(partner_id)),
        ], limit=1)

    def _channel_partner_ids(self, channel):
        if 'channel_partner_ids' in channel._fields:
            return channel.channel_partner_ids.ids
        if 'channel_member_ids' in channel._fields:
            return channel.channel_member_ids.mapped('partner_id').ids
        return []

    def _channel_has_partner(self, channel, partner):
        return partner.id in self._channel_partner_ids(channel)

    def _find_direct_channel(self, partner_a, partner_b):
        Channel = self._channel_model()
        domain = [('channel_type', '=', 'chat')]
        field_names = Channel._fields
        if 'channel_partner_ids' in field_names:
            domain += [('channel_partner_ids', 'in', [partner_a.id]), ('channel_partner_ids', 'in', [partner_b.id])]
        elif 'channel_member_ids' in field_names:
            domain += [('channel_member_ids.partner_id', 'in', [partner_a.id]), ('channel_member_ids.partner_id', 'in', [partner_b.id])]
        else:
            return Channel.browse()

        channels = Channel.search(domain, order='write_date desc', limit=20)
        for channel in channels:
            members = set(self._channel_partner_ids(channel))
            if {partner_a.id, partner_b.id}.issubset(members):
                return channel
        return Channel.browse()

    def _create_direct_channel(self, partner_a, partner_b):
        Channel = self._channel_model()
        vals = {
            'name': '%s, %s' % (partner_a.name or 'Employee', partner_b.name or 'Employee'),
        }
        if 'channel_type' in Channel._fields:
            vals['channel_type'] = 'chat'
        if 'channel_partner_ids' in Channel._fields:
            # Odoo 18 discuss.channel.create() expects ORM command tuples here.
            # A plain list of IDs raises: TypeError: 'int' object is not subscriptable.
            vals['channel_partner_ids'] = [(4, partner_a.id), (4, partner_b.id)]
        elif 'channel_member_ids' in Channel._fields:
            vals['channel_member_ids'] = [
                (0, 0, {'partner_id': partner_a.id}),
                (0, 0, {'partner_id': partner_b.id}),
            ]
        return Channel.create(vals)

    def _get_or_create_direct_channel(self, other_partner):
        my_partner = request.env.user.partner_id.sudo()
        channel = self._find_direct_channel(my_partner, other_partner.sudo())
        if channel:
            return channel
        return self._create_direct_channel(my_partner, other_partner.sudo())

    def _my_channels(self):
        partner = request.env.user.partner_id.sudo()
        Channel = self._channel_model()
        domain = [('channel_type', '=', 'chat')]
        if 'channel_partner_ids' in Channel._fields:
            domain.append(('channel_partner_ids', 'in', [partner.id]))
        elif 'channel_member_ids' in Channel._fields:
            domain.append(('channel_member_ids.partner_id', 'in', [partner.id]))
        else:
            return Channel.browse()
        return Channel.search(domain, order='write_date desc')

    def _last_read(self, channel):
        Read = request.env['employee.portal.message.read'].sudo()
        return Read.search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('channel_model', '=', channel._name),
            ('channel_id', '=', channel.id),
        ], limit=1)

    def _mark_read(self, channel):
        Read = request.env['employee.portal.message.read'].sudo()
        vals = {
            'partner_id': request.env.user.partner_id.id,
            'channel_model': channel._name,
            'channel_id': channel.id,
        }
        marker = Read.search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('channel_model', '=', channel._name),
            ('channel_id', '=', channel.id),
        ], limit=1)
        now = fields.Datetime.now()
        if marker:
            marker.write({'last_read_date': now})
        else:
            vals['last_read_date'] = now
            Read.create(vals)

    def _message_domain_for_channel(self, channel):
        return [
            ('model', '=', channel._name),
            ('res_id', '=', channel.id),
            ('message_type', '!=', 'notification'),
        ]

    def _unread_count(self, channel=None):
        Message = request.env['mail.message'].sudo()
        channels = channel or self._my_channels()
        count = 0
        for ch in channels:
            marker = self._last_read(ch)
            domain = self._message_domain_for_channel(ch) + [
                ('author_id', '!=', request.env.user.partner_id.id),
            ]
            if marker and marker.last_read_date:
                domain.append(('date', '>', marker.last_read_date))
            count += Message.search_count(domain)
        return count

    def _conversation_summary(self, channel):
        partner = request.env.user.partner_id.sudo()
        other_partners = request.env['res.partner'].sudo().browse([
            pid for pid in self._channel_partner_ids(channel) if pid != partner.id
        ])
        Message = request.env['mail.message'].sudo()
        last_message = Message.search(self._message_domain_for_channel(channel), order='date desc, id desc', limit=1)
        return {
            'channel': channel,
            'other_partners': other_partners,
            'title': ', '.join(other_partners.mapped('name')) or channel.name or 'Conversation',
            'last_message': last_message,
            'unread_count': self._unread_count(channel),
        }

    @http.route('/my/employee/messages/count', type='http', auth='user', website=False)
    def employee_portal_message_count(self):
        count = 0
        if self._my_employee():
            count = self._unread_count()
        return request.make_response(
            json.dumps({'count': count}),
            headers=[('Content-Type', 'application/json')]
        )

    @http.route(['/my/employee/messages'], type='http', auth='user', website=True)
    def employee_portal_messages(self, **kw):
        if not self._my_employee():
            return request.redirect('/my')
        conversations = [self._conversation_summary(c) for c in self._my_channels()]
        employees = self._messageable_employees().filtered(lambda e: e.user_id.id != request.env.user.id)
        return request.render('employee_portal_suite.employee_portal_messages', {
            'conversations': conversations,
            'employees': employees,
            'unread_total': self._unread_count(),
            'active_channel': False,
            'messages': request.env['mail.message'].sudo().browse(),
            'summary': False,
        })

    @http.route('/my/employee/messages/start', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def employee_portal_messages_start(self, partner_id=None, body=None, **kw):
        if not self._my_employee() or not partner_id:
            return request.redirect('/my/employee/messages')
        employee = self._employee_for_partner(partner_id)
        if not employee or employee.user_id.id == request.env.user.id:
            return request.redirect('/my/employee/messages')
        channel = self._get_or_create_direct_channel(employee.user_id.partner_id)
        if body:
            clean_body = Markup('<p>%s</p>' % html_escape(body).replace('\n', '<br/>'))
            channel.message_post(
                body=clean_body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=request.env.user.partner_id.id,
            )
        self._mark_read(channel)
        return request.redirect('/my/employee/messages/%s' % channel.id)

    @http.route('/my/employee/messages/<int:channel_id>', type='http', auth='user', website=True)
    def employee_portal_messages_thread(self, channel_id, **kw):
        if not self._my_employee():
            return request.redirect('/my')
        channel = self._channel_model().browse(channel_id)
        if not channel.exists() or not self._channel_has_partner(channel, request.env.user.partner_id):
            return request.redirect('/my/employee/messages')
        self._mark_read(channel)
        messages = request.env['mail.message'].sudo().search(
            self._message_domain_for_channel(channel),
            order='date asc, id asc'
        )
        conversations = [self._conversation_summary(c) for c in self._my_channels()]
        employees = self._messageable_employees().filtered(lambda e: e.user_id.id != request.env.user.id)
        return request.render('employee_portal_suite.employee_portal_messages', {
            'conversations': conversations,
            'employees': employees,
            'unread_total': self._unread_count(),
            'active_channel': channel,
            'channel': channel,
            'messages': messages,
            'summary': self._conversation_summary(channel),
        })

    @http.route('/my/employee/messages/<int:channel_id>/send', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def employee_portal_messages_send(self, channel_id, body=None, **kw):
        channel = self._channel_model().browse(channel_id)
        if channel.exists() and self._channel_has_partner(channel, request.env.user.partner_id) and body:
            clean_body = Markup('<p>%s</p>' % html_escape(body).replace('\n', '<br/>'))
            channel.message_post(
                body=clean_body,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=request.env.user.partner_id.id,
            )
            self._mark_read(channel)
        return request.redirect('/my/employee/messages/%s' % channel_id)
