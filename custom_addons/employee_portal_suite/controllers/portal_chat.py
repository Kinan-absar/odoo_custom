import base64
import binascii
import mimetypes
import re

from markupsafe import Markup

from odoo import fields, http, tools
from odoo.addons.mail.tools.discuss import Store
from odoo.http import request


MAX_CHAT_ATTACHMENT_BYTES = 10 * 1024 * 1024
ALLOWED_REACTIONS = {'👍', '❤️', '😂', '🎉', '😮', '😢', '🙏'}


class PortalChatController(http.Controller):

    def _user(self):
        return request.env.user

    def _is_employee_user(self, user):
        if not user or not user.active:
            return False
        return bool(request.env['hr.employee'].sudo().search_count([
            ('active', '=', True), ('user_id', '=', user.id),
        ]))

    def _employee_name(self, user):
        employee = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '=', user.id),
        ], limit=1)
        return employee.name or user.name or 'Employee'

    def _users_for_channel(self, channel):
        partners = channel.sudo().channel_member_ids.partner_id.filtered(lambda p: p.active)
        if len(partners) < 2:
            return request.env['res.users']
        users = request.env['res.users'].sudo().search([
            ('active', '=', True), ('partner_id', 'in', partners.ids),
        ])
        by_partner = {u.partner_id.id: u for u in users if self._is_employee_user(u)}
        if any(partner.id not in by_partner for partner in partners):
            return request.env['res.users']
        return request.env['res.users'].sudo().browse([by_partner[p.id].id for p in partners])

    def _channel_has_portal_employee(self, users):
        return any(bool(user.share) for user in users)

    def _sync_discuss_threads(self, user):
        """Expose only employee channels that genuinely belong to the portal bridge.

        Internal-only Discuss chats remain native Discuss-only. A channel is exposed
        when it is already explicitly marked or when at least one participant is an
        employee portal user (share=True).
        """
        Member = request.env['discuss.channel.member'].sudo()
        memberships = Member.search([
            ('partner_id', '=', user.partner_id.id),
            ('channel_id.channel_type', 'in', ['chat', 'group']),
        ])
        Thread = request.env['portal.chat.thread'].sudo()
        for channel in memberships.channel_id:
            users = self._users_for_channel(channel)
            if user not in users or len(users) < 2:
                continue
            if not channel.is_employee_portal_channel and not self._channel_has_portal_employee(users):
                continue

            thread = Thread.search([('discuss_channel_id', '=', channel.id)], limit=1)
            all_user_ids = sorted(users.ids)
            is_group = channel.channel_type == 'group' or len(all_user_ids) > 2
            direct_key = False if is_group else '%s:%s' % (all_user_ids[0], all_user_ids[1])

            if not thread and direct_key:
                thread = Thread.search([('direct_key', '=', direct_key)], limit=1)
                if thread and not thread.discuss_channel_id:
                    thread._bind_discuss_channel(channel)

            if not thread:
                other_users = users.filtered(lambda u: u.id != user.id)
                direct_name = self._employee_name(other_users[:1]) if other_users else 'Conversation'
                thread = Thread.create({
                    'name': (channel.name if is_group else direct_name) or 'Conversation',
                    'participant_ids': [(6, 0, all_user_ids)],
                    'is_group': is_group,
                    'direct_key': direct_key,
                    'discuss_channel_id': channel.id,
                    'last_message_date': channel.last_interest_dt or fields.Datetime.now(),
                })
            channel.sudo().write({
                'is_employee_portal_channel': True,
                'employee_portal_thread_id': thread.id,
            })
            vals = {}
            if set(thread.participant_ids.ids) != set(all_user_ids):
                vals['participant_ids'] = [(6, 0, all_user_ids)]
            if thread.is_group != is_group:
                vals['is_group'] = is_group
            if is_group and channel.name and thread.name != channel.name:
                vals['name'] = channel.name
            if vals:
                thread.write(vals)

    def _thread(self, thread_id):
        try:
            thread_id = int(thread_id or 0)
        except (TypeError, ValueError):
            return None
        thread = request.env['portal.chat.thread'].sudo().browse(thread_id).exists()
        user = self._user()
        if not thread or user.id not in thread.participant_ids.ids:
            return None
        channel = thread._ensure_discuss_channel()
        if not channel or user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
            return None
        return thread

    def _channel(self, thread):
        return thread._ensure_discuss_channel() if thread else request.env['discuss.channel']

    def _member(self, channel, user):
        return channel.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id.id == user.partner_id.id
        )[:1]

    def _announce_discuss_channel(self, channel):
        channel = channel.sudo().exists()
        if not channel:
            return
        members = channel.channel_member_ids.sudo().filtered(lambda m: m.partner_id)
        members.filtered(lambda m: m.unpin_dt).write({'unpin_dt': False})
        for member in members:
            if not member.partner_id.user_ids.filtered(lambda u: u.active and u._is_internal()):
                continue
            payload = {
                'channel': {
                    **channel._channel_basic_info(),
                    'model': 'discuss.channel',
                    'is_pinned': True,
                },
                'open_chat_window': False,
            }
            member._bus_send('discuss.channel/joined', payload)
        channel._broadcast(members.partner_id.ids)

    def _bridge_backend_users(self, channel, message, author_user):
        """Reliable fallback event for already-open backend clients.

        Native Discuss bus events remain authoritative. This extra personal-bus
        event lets our tiny backend bridge refresh an already-open Discuss screen
        when Odoo's store did not learn a portal-created channel in time.
        """
        for member in channel.sudo().channel_member_ids:
            for target in member.partner_id.user_ids.filtered(lambda u: u.active and u._is_internal()):
                if target.id == author_user.id:
                    continue
                target._bus_send('employee_portal_discuss_bridge', {
                    'channel_id': channel.id,
                    'message_id': message.id,
                    'author': self._employee_name(author_user),
                    'preview': tools.html2plaintext(message.body or '').strip()[:120],
                })

    def _mark_native_channel_seen(self, channel, user):
        member = self._member(channel, user)
        if not member:
            return
        latest = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
        ], order='id desc', limit=1)
        if latest:
            member._mark_as_read(latest.id, sync=True)

    def _read_state(self, thread, user, create=False):
        Read = request.env['portal.chat.read'].sudo()
        state = Read.search([('thread_id', '=', thread.id), ('user_id', '=', user.id)], limit=1)
        if not state and create:
            state = Read.create({
                'thread_id': thread.id, 'user_id': user.id,
                'last_read_at': fields.Datetime.now(),
            })
        return state

    def _unread_count(self, thread, user):
        channel = self._channel(thread)
        member = self._member(channel, user)
        if member:
            return int(member.message_unread_counter or 0)
        state = self._read_state(thread, user, create=False)
        domain = [
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'), ('author_id', '!=', user.partner_id.id),
        ]
        if state and state.last_read_at:
            domain.append(('date', '>', state.last_read_at))
        return request.env['mail.message'].sudo().search_count(domain)

    def _message_reactions(self, message, user):
        groups = {}
        reactions = request.env['mail.message.reaction'].sudo().search([
            ('message_id', '=', message.id),
        ], order='id asc')
        for reaction in reactions:
            item = groups.setdefault(reaction.content, {
                'content': reaction.content, 'count': 0, 'mine': False, 'names': [],
            })
            item['count'] += 1
            if reaction.partner_id:
                item['names'].append(reaction.partner_id.name)
                if reaction.partner_id.id == user.partner_id.id:
                    item['mine'] = True
        return list(groups.values())

    def _message_read_by(self, channel, message, user):
        names = []
        for member in channel.sudo().channel_member_ids:
            if member.partner_id.id == user.partner_id.id:
                continue
            if member.seen_message_id and member.seen_message_id.id >= message.id:
                names.append(member.partner_id.name)
        return names

    def _attachment_rows(self, message):
        return [{
            'id': att.id,
            'name': att.name or 'Attachment',
            'mimetype': att.mimetype or 'application/octet-stream',
            'size': att.file_size or 0,
            'url': '/employee_portal/chat/attachment/%s' % att.id,
        } for att in message.sudo().attachment_ids]

    def _message_row(self, msg, channel, user):
        author_user = request.env['res.users'].sudo().search([
            ('partner_id', '=', msg.author_id.id),
        ], limit=1)
        reply = None
        if msg.parent_id and msg.parent_id.model == 'discuss.channel' and msg.parent_id.res_id == channel.id:
            reply = {
                'id': msg.parent_id.id,
                'author': msg.parent_id.author_id.name or 'Employee',
                'body': tools.html2plaintext(msg.parent_id.body or '').strip()[:180],
            }
        return {
            'id': msg.id,
            'body': tools.html2plaintext(msg.body or '').strip(),
            'author': msg.author_id.name or 'Employee',
            'author_user_id': author_user.id or 0,
            'mine': msg.author_id.id == user.partner_id.id,
            'date': fields.Datetime.to_string(msg.date) if msg.date else '',
            'avatar_url': '/employee_portal/call/avatar/%s' % author_user.id if author_user else '',
            'attachments': self._attachment_rows(msg),
            'reply_to': reply,
            'reactions': self._message_reactions(msg, user),
            'read_by': self._message_read_by(channel, msg, user) if msg.author_id.id == user.partner_id.id else [],
        }

    def _telegram_new_message(self, channel, author_user, text):
        service = request.env['employee.portal.telegram.service'].sudo()
        title = 'New Odoo message'
        preview = (text or '').strip().replace('\n', ' ')[:160]
        for target in self._users_for_channel(channel).filtered(lambda u: u.id != author_user.id):
            service.send_to_user(
                target,
                title,
                '%s: %s' % (self._employee_name(author_user), preview or 'Sent an attachment'),
                path='/my/employee',
            )

    @http.route('/employee_portal/chat/threads', type='json', auth='user', csrf=False)
    def chat_threads(self):
        user = self._user()
        if not self._is_employee_user(user):
            return {'threads': [], 'unread_total': 0}
        self._sync_discuss_threads(user)
        threads = request.env['portal.chat.thread'].sudo().search([
            ('participant_ids', 'in', [user.id]),
        ], order='discuss_last_interest_dt desc, last_message_date desc, id desc', limit=60)
        result, unread_total = [], 0
        Message = request.env['mail.message'].sudo()
        for thread in threads:
            channel = self._channel(thread)
            if not channel or not channel.is_employee_portal_channel:
                continue
            users = self._users_for_channel(channel)
            if not users or user not in users:
                continue
            others = users.filtered(lambda u: u.id != user.id)
            names = [self._employee_name(u) for u in others]
            display_name = (channel.name or thread.name) if thread.is_group else (names[0] if names else thread.name)
            last = Message.search([
                ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
                ('message_type', '=', 'comment'),
            ], order='id desc', limit=1)
            preview = tools.html2plaintext(last.body or '').strip().replace('\n', ' ')[:100] if last else ''
            if last and last.attachment_ids and not preview:
                preview = 'Attachment: %s' % (last.attachment_ids[:1].name or 'file')
            unread = self._unread_count(thread, user)
            unread_total += unread
            avatar_uid = others[:1].id if len(others) else user.id
            result.append({
                'id': thread.id, 'name': display_name, 'is_group': thread.is_group,
                'participant_count': len(users), 'participant_ids': users.ids,
                'preview': preview, 'unread': unread,
                'last_message_date': fields.Datetime.to_string(channel.last_interest_dt) if channel.last_interest_dt else '',
                'avatar_url': '/employee_portal/call/avatar/%s' % avatar_uid,
                'discuss_channel_id': channel.id,
            })
        return {'threads': result, 'unread_total': unread_total}

    @http.route('/employee_portal/chat/start', type='json', auth='user', csrf=False)
    def chat_start(self, participant_ids=None, name=None):
        user = self._user()
        if not self._is_employee_user(user):
            return {'error': 'not_employee'}
        ids = []
        for raw in (participant_ids or []):
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                continue
            if uid != user.id and uid not in ids:
                target = request.env['res.users'].sudo().browse(uid).exists()
                if target and self._is_employee_user(target):
                    ids.append(uid)
        if not ids:
            return {'error': 'no_participants'}
        all_ids = sorted([user.id] + ids)
        Thread = request.env['portal.chat.thread'].sudo()
        is_group = len(all_ids) > 2
        if not is_group:
            direct_key = '%s:%s' % (all_ids[0], all_ids[1])
            thread = Thread.search([('direct_key', '=', direct_key)], limit=1)
            if not thread:
                other = request.env['res.users'].sudo().browse(ids[0])
                thread = Thread.create({
                    'name': self._employee_name(other),
                    'participant_ids': [(6, 0, all_ids)], 'is_group': False,
                    'direct_key': direct_key,
                })
        else:
            names = [self._employee_name(request.env['res.users'].sudo().browse(uid)) for uid in ids]
            requested_name = (name or '').strip()
            default_name = ', '.join(names[:3]) + (' +%s' % (len(names)-3) if len(names) > 3 else '')
            thread = Thread.create({
                'name': (requested_name or default_name or 'Group chat')[:120],
                'participant_ids': [(6, 0, all_ids)], 'is_group': True,
            })
        channel = thread._ensure_discuss_channel()
        if not channel:
            return {'error': 'discuss_channel_failed'}
        channel.sudo().write({'is_employee_portal_channel': True, 'employee_portal_thread_id': thread.id})
        self._read_state(thread, user, create=True)
        return {'thread_id': thread.id, 'discuss_channel_id': channel.id}

    @http.route('/employee_portal/chat/messages', type='json', auth='user', csrf=False)
    def chat_messages(self, thread_id=None, limit=80):
        thread = self._thread(thread_id)
        if not thread:
            return {'error': 'not_found', 'messages': []}
        user, channel = self._user(), self._channel(thread)
        messages = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
        ], order='id desc', limit=min(int(limit or 80), 150))
        rows = [self._message_row(msg, channel, user) for msg in reversed(messages)]
        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        self._mark_native_channel_seen(channel, user)
        users = self._users_for_channel(channel)
        participants = [{
            'user_id': participant.id,
            'name': self._employee_name(participant),
            'avatar_url': '/employee_portal/call/avatar/%s' % participant.id,
            'is_me': participant.id == user.id,
        } for participant in users]
        now = fields.Datetime.now()
        typing = []
        for member in channel.sudo().channel_member_ids:
            if member.partner_id.id == user.partner_id.id or not member.portal_is_typing:
                continue
            if member.portal_typing_dt and (now - member.portal_typing_dt).total_seconds() <= 8:
                typing.append(member.partner_id.name)
        return {
            'thread': {
                'id': thread.id,
                'name': (channel.name or thread.name) if thread.is_group else thread.name,
                'is_group': thread.is_group, 'participant_ids': users.ids,
                'participant_count': len(users), 'participants': participants,
                'discuss_channel_id': channel.id,
            },
            'messages': rows,
            'typing': typing,
        }

    def _validate_reply(self, channel, reply_to_id):
        if not reply_to_id:
            return request.env['mail.message']
        try:
            mid = int(reply_to_id)
        except (TypeError, ValueError):
            return request.env['mail.message']
        return request.env['mail.message'].sudo().search([
            ('id', '=', mid), ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
        ], limit=1)

    def _prepare_mentions(self, channel, text):
        mentioned_partners = request.env['res.partner']
        for user in self._users_for_channel(channel):
            name = self._employee_name(user)
            if re.search(r'(?<!\w)@' + re.escape(name) + r'\b', text, flags=re.I):
                mentioned_partners |= user.partner_id
        return mentioned_partners

    @http.route('/employee_portal/chat/send', type='json', auth='user', csrf=False)
    def chat_send(self, thread_id=None, body=None, reply_to_id=None, attachment_ids=None):
        thread = self._thread(thread_id)
        text = (body or '').strip()
        if not thread or (not text and not attachment_ids):
            return {'error': 'invalid'}
        user, channel = self._user(), self._channel(thread)
        self._announce_discuss_channel(channel)
        reply = self._validate_reply(channel, reply_to_id)
        attachments = request.env['ir.attachment'].sudo().browse([
            int(x) for x in (attachment_ids or []) if str(x).isdigit()
        ]).exists().filtered(lambda a: a.res_model == 'discuss.channel' and a.res_id == channel.id)
        mentioned = self._prepare_mentions(channel, text)
        body_html = Markup.escape(text).replace('\n', Markup('<br/>')) if text else Markup('')
        message = channel.with_user(user).sudo().message_post(
            body=body_html,
            message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=user.partner_id.id,
            attachment_ids=attachments.ids,
            parent_id=reply.id or False,
            partner_ids=mentioned.ids,
        )
        self._announce_discuss_channel(channel)
        self._bridge_backend_users(channel, message, user)
        thread.sudo().write({'last_message_date': fields.Datetime.now()})
        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        self._mark_native_channel_seen(channel, user)
        self._telegram_new_message(channel, user, text)
        return {'ok': True, 'message_id': message.id, 'discuss_channel_id': channel.id}

    @http.route('/employee_portal/chat/upload', type='json', auth='user', csrf=False)
    def chat_upload(self, thread_id=None, filename=None, mimetype=None, data=None):
        thread = self._thread(thread_id)
        if not thread:
            return {'error': 'not_found'}
        filename = (filename or 'attachment').strip()[:180]
        raw = data or ''
        if ',' in raw and raw.lstrip().startswith('data:'):
            raw = raw.split(',', 1)[1]
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            return {'error': 'invalid_file'}
        if not decoded or len(decoded) > MAX_CHAT_ATTACHMENT_BYTES:
            return {'error': 'file_too_large'}
        channel = self._channel(thread)
        mime = (mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream')[:128]
        attachment = request.env['ir.attachment'].sudo().create({
            'name': filename,
            'datas': base64.b64encode(decoded),
            'mimetype': mime,
            'res_model': 'discuss.channel',
            'res_id': channel.id,
        })
        return {'ok': True, 'attachment': {
            'id': attachment.id, 'name': attachment.name, 'mimetype': attachment.mimetype,
            'size': attachment.file_size or len(decoded),
        }}

    @http.route('/employee_portal/chat/attachment/<int:attachment_id>', type='http', auth='user', csrf=False)
    def chat_attachment(self, attachment_id, **kwargs):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != 'discuss.channel':
            return request.not_found()
        channel = request.env['discuss.channel'].sudo().browse(attachment.res_id).exists()
        user = self._user()
        if not channel or user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
            return request.not_found()
        raw = base64.b64decode(attachment.datas or b'')
        headers = [
            ('Content-Type', attachment.mimetype or 'application/octet-stream'),
            ('Content-Length', str(len(raw))),
            ('Content-Disposition', 'attachment; filename="%s"' % (attachment.name or 'attachment').replace('"', '')),
        ]
        return request.make_response(raw, headers=headers)

    @http.route('/employee_portal/chat/reaction', type='json', auth='user', csrf=False)
    def chat_reaction(self, thread_id=None, message_id=None, content=None, action='add'):
        thread = self._thread(thread_id)
        if not thread or content not in ALLOWED_REACTIONS or action not in ('add', 'remove'):
            return {'error': 'invalid'}
        channel = self._channel(thread)
        message = request.env['mail.message'].sudo().search([
            ('id', '=', int(message_id or 0)), ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
        ], limit=1)
        if not message:
            return {'error': 'not_found'}
        user = self._user()
        message.sudo()._message_reaction(
            content, action, user.partner_id.sudo(), request.env['mail.guest'], Store()
        )
        return {'ok': True, 'reactions': self._message_reactions(message, user)}

    @http.route('/employee_portal/chat/typing', type='json', auth='user', csrf=False)
    def chat_typing(self, thread_id=None, typing=False):
        thread = self._thread(thread_id)
        if not thread:
            return {'ok': False}
        user, channel = self._user(), self._channel(thread)
        member = self._member(channel, user)
        if not member:
            return {'ok': False}
        member.sudo().write({
            'portal_is_typing': bool(typing),
            'portal_typing_dt': fields.Datetime.now(),
        })
        try:
            member.with_user(user)._notify_typing(bool(typing))
        except Exception:
            pass
        return {'ok': True}

    @http.route('/employee_portal/chat/mark_read', type='json', auth='user', csrf=False)
    def chat_mark_read(self, thread_id=None):
        thread = self._thread(thread_id)
        if not thread:
            return {'ok': False}
        user = self._user()
        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        self._mark_native_channel_seen(self._channel(thread), user)
        return {'ok': True}
