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

    def _thread(self, thread_id):
        thread = request.env['portal.chat.thread'].sudo().browse(int(thread_id or 0)).exists()
        if not thread or self._user().id not in thread.participant_ids.ids:
            return None
        return thread

    def _read_state(self, thread, user, create=False):
        Read = request.env['portal.chat.read'].sudo()
        state = Read.search([('thread_id', '=', thread.id), ('user_id', '=', user.id)], limit=1)
        if not state and create:
            state = Read.create({'thread_id': thread.id, 'user_id': user.id, 'last_read_at': fields.Datetime.now()})
        return state

    def _unread_count(self, thread, user):
        state = self._read_state(thread, user, create=False)
        domain = [
            ('model', '=', 'portal.chat.thread'),
            ('res_id', '=', thread.id),
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
        threads = request.env['portal.chat.thread'].sudo().search([
            ('participant_ids', 'in', [user.id]),
        ], order='last_message_date desc, id desc', limit=60)
        result = []
        unread_total = 0
        Message = request.env['mail.message'].sudo()
        for thread in threads:
            others = thread.participant_ids.filtered(lambda u: u.id != user.id)
            names = [self._employee_name(u) for u in others]
            display_name = thread.name if thread.is_group else (names[0] if names else thread.name)
            last = Message.search([
                ('model', '=', 'portal.chat.thread'), ('res_id', '=', thread.id), ('message_type', '=', 'comment'),
            ], order='id desc', limit=1)
            preview = tools.html2plaintext(last.body or '').strip().replace('\n', ' ')[:100] if last else ''
            unread = self._unread_count(thread, user)
            unread_total += unread
            avatar_uid = others[:1].id if len(others) else user.id
            result.append({
                'id': thread.id,
                'name': display_name,
                'is_group': thread.is_group,
                'participant_count': len(thread.participant_ids),
                'participant_ids': thread.participant_ids.ids,
                'preview': preview,
                'unread': unread,
                'last_message_date': fields.Datetime.to_string(thread.last_message_date) if thread.last_message_date else '',
                'avatar_url': '/employee_portal/call/avatar/%s' % avatar_uid,
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
            thread = Thread.create({
                'name': (name or ', '.join(names[:3]) + (' +%s' % (len(names)-3) if len(names) > 3 else ''))[:120],
                'participant_ids': [(6, 0, all_ids)],
                'is_group': True,
            })
        self._read_state(thread, user, create=True)
        return {'thread_id': thread.id}

    @http.route('/employee_portal/chat/messages', type='json', auth='user', csrf=False)
    def chat_messages(self, thread_id=None, limit=80):
        thread = self._thread(thread_id)
        if not thread:
            return {'error': 'not_found', 'messages': []}
        user = self._user()
        messages = request.env['mail.message'].sudo().search([
            ('model', '=', 'portal.chat.thread'),
            ('res_id', '=', thread.id),
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
        return {
            'thread': {'id': thread.id, 'name': thread.name, 'is_group': thread.is_group, 'participant_ids': thread.participant_ids.ids},
            'messages': rows,
        }

    @http.route('/employee_portal/chat/send', type='json', auth='user', csrf=False)
    def chat_send(self, thread_id=None, body=None):
        thread = self._thread(thread_id)
        text = (body or '').strip()
        if not thread or not text:
            return {'error': 'invalid'}
        user = self._user()
        message = thread.sudo().message_post(
            body=Markup.escape(text).replace('\n', Markup('<br/>')),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=user.partner_id.id,
        )
        thread.sudo().write({'last_message_date': fields.Datetime.now()})
        state = self._read_state(thread, user, create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        return {'ok': True, 'message_id': message.id}

    @http.route('/employee_portal/chat/mark_read', type='json', auth='user', csrf=False)
    def chat_mark_read(self, thread_id=None):
        thread = self._thread(thread_id)
        if not thread:
            return {'ok': False}
        state = self._read_state(thread, self._user(), create=True)
        state.write({'last_read_at': fields.Datetime.now()})
        return {'ok': True}
