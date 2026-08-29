from markupsafe import Markup

from odoo import fields, http, tools
from odoo.http import request


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
        """Return active employee users represented by a private Discuss channel."""
        partners = channel.sudo().channel_member_ids.partner_id.filtered(lambda p: p.active)
        if len(partners) < 2:
            return request.env['res.users']
        users = request.env['res.users'].sudo().search([
            ('active', '=', True),
            ('partner_id', 'in', partners.ids),
        ])
        by_partner = {u.partner_id.id: u for u in users if self._is_employee_user(u)}
        # Do not expose mixed/customer Discuss chats in the employee portal.
        if any(partner.id not in by_partner for partner in partners):
            return request.env['res.users']
        return request.env['res.users'].sudo().browse([by_partner[p.id].id for p in partners])

    def _sync_discuss_threads(self, user):
        """Discover native Discuss chats started by internal users.

        This is what makes the integration truly two-way: an internal employee can
        start a normal Odoo Discuss DM/group and the portal employee will discover
        the same conversation in the custom portal Messages UI.
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
            # Once a native Discuss conversation is exposed to an employee
            # portal participant it becomes an explicitly portal-linked channel.
            channel.sudo().write({
                'is_employee_portal_channel': True,
                'employee_portal_thread_id': thread.id,
            })

            if thread:
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
        thread = request.env['portal.chat.thread'].sudo().browse(int(thread_id or 0)).exists()
        user = self._user()
        if not thread or user.id not in thread.participant_ids.ids:
            return None
        channel = thread._ensure_discuss_channel()
        if not channel:
            return None
        # Membership in Discuss is authoritative once the wrapper is linked.
        if user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
            return None
        return thread

    def _channel(self, thread):
        return thread._ensure_discuss_channel() if thread else request.env['discuss.channel']


    def _announce_discuss_channel(self, channel, author_user=None):
        """Push a native Discuss join/header event to internal employee members.

        Portal-created private channels can exist in the database before an already
        open backend Discuss store knows about them. Odoo normally sends
        ``discuss.channel/joined`` when add_members() creates membership. Our
        portal wrapper can bind/create channels outside that exact UI flow, so we
        explicitly emit the same event on each internal member's personal bus.
        This makes the backend load the thread before the native new_message event.
        """
        channel = channel.sudo().exists()
        if not channel:
            return
        members = channel.channel_member_ids.sudo().filtered(lambda m: m.partner_id)
        # Keep members pinned so chat/group channels are part of Discuss' active set.
        members.filtered(lambda m: m.unpin_dt).write({'unpin_dt': False})
        for member in members:
            target_users = member.partner_id.user_ids.filtered(
                lambda u: u.active and u._is_internal()
            )
            if not target_users:
                continue
            payload = {
                'channel': {
                    **channel._channel_basic_info(),
                    'model': 'discuss.channel',
                    'is_pinned': True,
                },
                'open_chat_window': False,
            }
            # This is intentionally sent through the member listener, matching
            # Odoo's native discuss.channel._add_members() behavior.
            member._bus_send('discuss.channel/joined', payload)
        # Also broadcast the full channel Store header on each user's personal bus.
        channel._broadcast(members.partner_id.ids)

    def _mark_native_channel_seen(self, channel, user):
        """Keep native Discuss member read state aligned with the portal UI."""
        channel = channel.sudo().exists()
        if not channel or not user or not user.partner_id:
            return
        member = channel.channel_member_ids.sudo().filtered(
            lambda m: m.partner_id.id == user.partner_id.id
        )[:1]
        if not member:
            return
        latest = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
        ], order='id desc', limit=1)
        if latest:
            member._set_last_seen_message(latest, notify=True)
            member._set_new_message_separator(latest.id + 1, sync=True)

    def _read_state(self, thread, user, create=False):
        Read = request.env['portal.chat.read'].sudo()
        state = Read.search([('thread_id', '=', thread.id), ('user_id', '=', user.id)], limit=1)
        if not state and create:
            state = Read.create({'thread_id': thread.id, 'user_id': user.id, 'last_read_at': fields.Datetime.now()})
        return state

    def _unread_count(self, thread, user):
        channel = self._channel(thread)
        if not channel:
            return 0
        state = self._read_state(thread, user, create=False)
        domain = [
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
            ('author_id', '!=', user.partner_id.id),
        ]
        if state and state.last_read_at:
            domain.append(('date', '>', state.last_read_at))
        return request.env['mail.message'].sudo().search_count(domain)

    @http.route('/employee_portal/chat/threads', type='json', auth='user', csrf=False)
    def chat_threads(self):
        user = self._user()
        if not self._is_employee_user(user):
            return {'threads': [], 'unread_total': 0}

        self._sync_discuss_threads(user)
        threads = request.env['portal.chat.thread'].sudo().search([
            ('participant_ids', 'in', [user.id]),
        ], order='discuss_last_interest_dt desc, last_message_date desc, id desc', limit=60)

        result = []
        unread_total = 0
        Message = request.env['mail.message'].sudo()
        for thread in threads:
            channel = self._channel(thread)
            if not channel or user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
                continue
            users = self._users_for_channel(channel)
            if not users:
                continue
            others = users.filtered(lambda u: u.id != user.id)
            names = [self._employee_name(u) for u in others]
            display_name = (channel.name or thread.name) if thread.is_group else (names[0] if names else thread.name)
            last = Message.search([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', channel.id),
                ('message_type', '=', 'comment'),
            ], order='id desc', limit=1)
            preview = tools.html2plaintext(last.body or '').strip().replace('\n', ' ')[:100] if last else ''
            unread = self._unread_count(thread, user)
            unread_total += unread
            avatar_uid = others[:1].id if len(others) else user.id
            result.append({
                'id': thread.id,
                'name': display_name,
                'is_group': thread.is_group,
                'participant_count': len(users),
                'participant_ids': users.ids,
                'preview': preview,
                'unread': unread,
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
                    'participant_ids': [(6, 0, all_ids)],
                    'is_group': False,
                    'direct_key': direct_key,
                })
        else:
            names = [self._employee_name(request.env['res.users'].sudo().browse(uid)) for uid in ids]
            requested_name = (name or '').strip()
            default_name = ', '.join(names[:3]) + (' +%s' % (len(names)-3) if len(names) > 3 else '')
            thread = Thread.create({
                'name': (requested_name or default_name or 'Group chat')[:120],
                'participant_ids': [(6, 0, all_ids)],
                'is_group': True,
            })

        channel = thread._ensure_discuss_channel()
        if not channel:
            return {'error': 'discuss_channel_failed'}
        self._read_state(thread, user, create=True)
        return {'thread_id': thread.id, 'discuss_channel_id': channel.id}

    @http.route('/employee_portal/chat/messages', type='json', auth='user', csrf=False)
    def chat_messages(self, thread_id=None, limit=80):
        thread = self._thread(thread_id)
        if not thread:
            return {'error': 'not_found', 'messages': []}
        user = self._user()
        channel = self._channel(thread)
        messages = request.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
        ], order='id desc', limit=min(int(limit or 80), 150))
        rows = []
        for msg in reversed(messages):
            author_user = request.env['res.users'].sudo().search([('partner_id', '=', msg.author_id.id)], limit=1)
            rows.append({
                'id': msg.id,
                'body': tools.html2plaintext(msg.body or '').strip(),
                'author': msg.author_id.name or 'Employee',
                'author_user_id': author_user.id or 0,
                'mine': msg.author_id.id == user.partner_id.id,
                'date': fields.Datetime.to_string(msg.date) if msg.date else '',
                'avatar_url': '/employee_portal/call/avatar/%s' % author_user.id if author_user else '',
            })

        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        self._mark_native_channel_seen(channel, user)
        users = self._users_for_channel(channel)
        participants = []
        for participant in users:
            participants.append({
                'user_id': participant.id,
                'name': self._employee_name(participant),
                'avatar_url': '/employee_portal/call/avatar/%s' % participant.id,
                'is_me': participant.id == user.id,
            })
        return {
            'thread': {
                'id': thread.id,
                'name': (channel.name or thread.name) if thread.is_group else thread.name,
                'is_group': thread.is_group,
                'participant_ids': users.ids,
                'participant_count': len(users),
                'participants': participants,
                'discuss_channel_id': channel.id,
            },
            'messages': rows,
        }

    @http.route('/employee_portal/chat/send', type='json', auth='user', csrf=False)
    def chat_send(self, thread_id=None, body=None):
        thread = self._thread(thread_id)
        text = (body or '').strip()
        if not thread or not text:
            return {'error': 'invalid'}
        user = self._user()
        channel = self._channel(thread)

        # Make sure an already-open backend Discuss store knows the private
        # channel before Odoo emits its native discuss.channel/new_message event.
        self._announce_discuss_channel(channel, author_user=user)

        # Keep the request user as the current persona while using sudo access.
        # Discuss' post hooks use the current persona to set sender-side seen state.
        message = channel.with_user(user).sudo().message_post(
            body=Markup.escape(text).replace('\n', Markup('<br/>')),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=user.partner_id.id,
        )

        # Re-announce after posting so personal-bus subscribers also receive the
        # fresh unread/member Store values in the same transaction.
        self._announce_discuss_channel(channel, author_user=user)
        thread.sudo().write({'last_message_date': fields.Datetime.now()})
        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        return {'ok': True, 'message_id': message.id, 'discuss_channel_id': channel.id}

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
