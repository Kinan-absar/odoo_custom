from odoo import Command, fields, http
from odoo.http import request
from odoo.addons.mail.tools.discuss import Store
from odoo.tools.image import image_data_uri


class EmployeePortalNativeDiscussController(http.Controller):

    def _employee_user(self):
        user = request.env.user
        if user._is_public() or not user.active:
            return False
        employee = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '=', user.id),
        ], limit=1)
        if not employee:
            return False
        if user.has_group('employee_portal_suite.group_attendance_only'):
            return False
        return user

    def _employee_users(self):
        employees = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '!=', False),
        ])
        users = employees.mapped('user_id').filtered(lambda u: u.active and u.partner_id)
        return users.sorted(lambda u: (u.name or '').lower())

    def _channel_users(self, channel):
        partners = channel.sudo().channel_member_ids.partner_id.filtered(lambda p: p.active)
        if not partners:
            return request.env['res.users']
        users = request.env['res.users'].sudo().search([
            ('active', '=', True), ('partner_id', 'in', partners.ids),
        ])
        employee_user_ids = set(self._employee_users().ids)
        return users.filtered(lambda u: u.id in employee_user_ids)

    def _is_allowed_channel(self, channel, user):
        channel = channel.sudo().exists()
        if not channel or channel.channel_type not in ('chat', 'group'):
            return False
        if user.partner_id not in channel.channel_member_ids.partner_id:
            return False
        users = self._channel_users(channel)
        if user not in users or len(users) < 2:
            return False
        # Native internal-only Discuss chats remain backend-only. Portal exposure is
        # explicit or automatic when at least one employee participant is a portal user.
        return bool(channel.is_employee_portal_channel or any(u.share for u in users))

    def _ensure_legacy_channels(self, user):
        # One-time compatibility bridge for conversations created by the old portal
        # chat implementation. It only ensures their canonical Discuss channel exists;
        # the old frontend is no longer used.
        legacy = request.env['portal.chat.thread'].sudo().search([
            ('participant_ids', 'in', [user.id]),
        ])
        for thread in legacy:
            try:
                thread._ensure_discuss_channel()
            except Exception:
                continue

    def _portal_channels(self, user):
        self._ensure_legacy_channels(user)
        members = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', user.partner_id.id),
            ('channel_id.channel_type', 'in', ('chat', 'group')),
        ])
        channels = members.channel_id.filtered(lambda c: self._is_allowed_channel(c, user))
        ordered = sorted(
            channels,
            key=lambda c: c.last_interest_dt or fields.Datetime.from_string('1970-01-01 00:00:00'),
            reverse=True,
        )
        return request.env['discuss.channel'].sudo().browse([c.id for c in ordered])

    def _channel_label(self, channel, user):
        users = self._channel_users(channel)
        others = users.filtered(lambda u: u.id != user.id)
        if channel.channel_type == 'group' or len(users) > 2:
            return channel.name or ', '.join(others.mapped('name')) or 'Group'
        return others[:1].name or channel.name or 'Conversation'

    def _user_avatar(self, user):
        """Return an inline avatar so portal record rules cannot block employee photos."""
        if not user or not user.partner_id:
            return False
        avatar = user.partner_id.sudo().avatar_128
        return image_data_uri(avatar) if avatar else False

    def _channel_avatar(self, channel, user):
        users = self._channel_users(channel)
        others = users.filtered(lambda u: u.id != user.id)
        if channel.channel_type == 'group' or len(users) > 2:
            return False
        return self._user_avatar(others[:1]) if others else False

    def _find_exact_dm(self, partner_ids):
        partner_ids = sorted(set(int(pid) for pid in partner_ids if pid))
        if len(partner_ids) != 2:
            return request.env['discuss.channel']
        request.env['discuss.channel'].flush_model()
        request.env['discuss.channel.member'].flush_model()
        request.env.cr.execute("""
            SELECT c.id
              FROM discuss_channel c
              JOIN discuss_channel_member m ON m.channel_id = c.id
             WHERE c.channel_type = 'chat'
               AND m.partner_id IN %s
               AND NOT EXISTS (
                    SELECT 1 FROM discuss_channel_member mx
                     WHERE mx.channel_id = c.id AND mx.partner_id NOT IN %s
               )
          GROUP BY c.id
            HAVING ARRAY_AGG(DISTINCT m.partner_id ORDER BY m.partner_id) = %s
             LIMIT 1
        """, (tuple(partner_ids), tuple(partner_ids), partner_ids))
        row = request.env.cr.fetchone()
        return request.env['discuss.channel'].sudo().browse(row[0]) if row else request.env['discuss.channel']

    def _get_or_create_channel(self, user, target_users, name=None):
        """Use Odoo's native DM creation path and a true group for 3+ people."""
        target_users = target_users.filtered(lambda u: u.active and u.partner_id and u.id != user.id)
        if not target_users:
            return request.env['discuss.channel']

        # Direct conversation: delegate completely to native Odoo channel_get().
        # sudo keeps the current uid in Odoo 18, so the portal employee remains
        # the current persona while ACLs are bypassed for the server-side bridge.
        if len(target_users) == 1:
            target_partner_id = target_users.partner_id.id
            channel = request.env['discuss.channel'].sudo().channel_get([target_partner_id])
            channel.sudo().write({
                'is_employee_portal_channel': True,
                'last_interest_dt': fields.Datetime.now(),
            })
            member = channel.channel_member_ids.filtered(
                lambda m: m.partner_id.id == user.partner_id.id
            )[:1]
            if member:
                member.sudo().write({'unpin_dt': False})
            return channel

        # Group conversation: create a native `group` channel with every member
        # on the initial create. Never create a `chat` and then append members.
        all_users = (user | target_users).filtered(lambda u: u.active and u.partner_id)
        partner_ids = sorted(set(all_users.partner_id.ids))
        now = fields.Datetime.now()
        channel = request.env['discuss.channel'].sudo().create({
            'channel_type': 'group',
            'name': (name or '').strip() or ', '.join(target_users.mapped('name')),
            'is_employee_portal_channel': True,
            'channel_member_ids': [
                Command.create({
                    'partner_id': partner_id,
                    'unpin_dt': False if partner_id == user.partner_id.id else now,
                    'last_interest_dt': now,
                })
                for partner_id in partner_ids
            ],
        })
        channel.sudo()._broadcast(partner_ids)
        return channel

    @http.route('/my/employee/discuss', type='http', auth='user', website=True, methods=['GET'])
    def employee_discuss_hub(self, **kwargs):
        user = self._employee_user()
        if not user:
            return request.redirect('/my/employee')
        channels = self._portal_channels(user)
        rows = []
        for channel in channels:
            member = channel.channel_member_ids.filtered(lambda m: m.partner_id.id == user.partner_id.id)[:1]
            rows.append({
                'id': channel.id,
                'name': self._channel_label(channel, user),
                'avatar': self._channel_avatar(channel, user),
                'is_group': channel.channel_type == 'group' or len(self._channel_users(channel)) > 2,
                'unread': int(member.message_unread_counter or 0),
                'last_interest_dt': channel.last_interest_dt,
            })
        employee_rows = []
        for emp_user in self._employee_users().filtered(lambda u: u.id != user.id):
            employee_rows.append({
                'id': emp_user.id,
                'name': emp_user.name,
                'avatar': self._user_avatar(emp_user),
            })
        values = {
            'channels': rows,
            'employees': employee_rows,
            'call_mode': kwargs.get('mode') == 'call',
        }
        # Keep all normal portal layout counters/notification context.
        try:
            values.update(request.env['ir.http']._prepare_portal_layout_values())
        except Exception:
            pass
        return request.render('employee_portal_suite.employee_native_discuss_hub', values)

    @http.route('/my/employee/discuss/start', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def employee_discuss_start(self, participant_ids=None, group_name=None, **post):
        user = self._employee_user()
        if not user:
            return request.redirect('/my/employee')
        raw_ids = request.httprequest.form.getlist('participant_ids')
        try:
            ids = [int(x) for x in raw_ids if x]
        except (TypeError, ValueError):
            ids = []
        allowed = self._employee_users().filtered(lambda u: u.id != user.id)
        targets = allowed.filtered(lambda u: u.id in ids)
        channel = self._get_or_create_channel(user, targets, name=group_name)
        if not channel:
            return request.redirect('/my/employee/discuss')
        return request.redirect(f'/my/employee/discuss/channel/{channel.id}')

    @http.route('/my/employee/discuss/channel/<int:channel_id>', type='http', auth='user', website=True, methods=['GET'])
    def employee_discuss_channel(self, channel_id, **kwargs):
        user = self._employee_user()
        if not user:
            return request.redirect('/my/employee')
        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not self._is_allowed_channel(channel, user):
            return request.not_found()
        channel.sudo().write({'is_employee_portal_channel': True})

        # Use Odoo's real public Discuss frontend and Store. This is the same native
        # frontend Odoo uses for /discuss/channel and it includes the native RTC stack.
        channel_user = channel.with_user(user)
        store = Store()
        store.add({
            'companyName': request.env.company.name,
            'inPublicPage': True,
            'employeePortalDiscuss': True,
            'employeePortalBackUrl': '/my/employee/discuss',
            'discuss_public_thread': Store.one(channel_user),
        })
        return request.render('mail.discuss_public_channel_template', {
            'data': store.get_result(),
            'session_info': channel_user.env['ir.http'].session_info(),
            'employee_portal_discuss': True,
            'employee_portal_back_url': '/my/employee/discuss',
            'employee_portal_home_url': '/my/employee',
        })

    @http.route('/employee_portal/discuss/available_people', type='json', auth='user')
    def employee_discuss_available_people(self, channel_id=None):
        user = self._employee_user()
        if not user:
            return {'people': []}
        try:
            channel_id = int(channel_id or 0)
        except (TypeError, ValueError):
            channel_id = 0
        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not self._is_allowed_channel(channel, user):
            return {'people': []}
        existing_ids = set(self._channel_users(channel).ids)
        people = []
        for emp_user in self._employee_users():
            if emp_user.id == user.id or emp_user.id in existing_ids:
                continue
            people.append({
                'id': emp_user.id,
                'name': emp_user.name,
                'avatar': self._user_avatar(emp_user),
            })
        return {'people': people}

    @http.route('/employee_portal/discuss/add_people', type='json', auth='user')
    def employee_discuss_add_people(self, channel_id=None, user_ids=None):
        user = self._employee_user()
        if not user:
            return {'ok': False, 'error': 'Employee access required.'}
        try:
            channel_id = int(channel_id or 0)
        except (TypeError, ValueError):
            channel_id = 0
        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not self._is_allowed_channel(channel, user):
            return {'ok': False, 'error': 'Conversation not available.'}
        try:
            wanted_ids = {int(x) for x in (user_ids or []) if x}
        except (TypeError, ValueError):
            wanted_ids = set()
        if not wanted_ids:
            return {'ok': False, 'error': 'Select at least one employee.'}
        allowed = self._employee_users().filtered(lambda u: u.id != user.id and u.id in wanted_ids)
        if not allowed:
            return {'ok': False, 'error': 'No valid employees selected.'}

        existing_users = self._channel_users(channel)
        new_users = allowed - existing_users
        if not new_users:
            return {'ok': True, 'channel_id': channel.id}

        # A native 2-person `chat` cannot accept a third member. Promote it to
        # a new native `group` with the existing correspondent plus the selected employees.
        if channel.channel_type == 'chat':
            current_others = existing_users.filtered(lambda u: u.id != user.id)
            targets = current_others | new_users
            group = self._get_or_create_channel(user, targets)
            if not group:
                return {'ok': False, 'error': 'Unable to create group conversation.'}
            return {
                'ok': True,
                'channel_id': group.id,
                'redirect': f'/my/employee/discuss/channel/{group.id}',
            }

        # For a native group, use Odoo's own member-add path so joined events,
        # member count and realtime channel state are broadcast normally.
        channel.with_user(user).sudo()._add_members(
            partners=new_users.partner_id,
            inviting_partner=user.partner_id,
        )
        channel.sudo().write({
            'is_employee_portal_channel': True,
            'last_interest_dt': fields.Datetime.now(),
        })
        return {'ok': True, 'channel_id': channel.id}

    @http.route('/employee_portal/discuss/unread', type='json', auth='user')
    def employee_discuss_unread(self):
        user = self._employee_user()
        if not user:
            return {'unread': 0}
        channels = self._portal_channels(user)
        members = channels.channel_member_ids.filtered(lambda m: m.partner_id.id == user.partner_id.id)
        return {'unread': sum(int(m.message_unread_counter or 0) for m in members)}

    @http.route('/employee_portal/discuss/call/poll', type='json', auth='user', csrf=False)
    def employee_discuss_call_poll(self):
        """Expose native Discuss RTC invitations to the employee portal shell.

        This does not create or join calls.  It only mirrors Odoo's native
        rtc_inviting_session_id state so a portal employee can see that a call
        is ringing before opening the public Discuss page.
        """
        user = self._employee_user()
        if not user:
            return {'call': False}
        member = request.env['discuss.channel.member'].sudo().search([
            ('partner_id', '=', user.partner_id.id),
            ('rtc_inviting_session_id', '!=', False),
        ], order='id desc', limit=1)
        if not member or not self._is_allowed_channel(member.channel_id, user):
            return {'call': False}
        session = member.rtc_inviting_session_id.sudo()
        caller_member = session.channel_member_id.sudo()
        caller_partner = caller_member.partner_id.sudo()
        caller_user = caller_partner.user_ids.filtered(lambda u: u.active)[:1]
        return {
            'call': {
                'channel_id': member.channel_id.id,
                'channel_name': self._channel_label(member.channel_id, user),
                'caller_name': caller_partner.name or self._channel_label(member.channel_id, user),
                'caller_avatar': self._user_avatar(caller_user) if caller_user else False,
                'is_video': bool(session.is_camera_on),
                'open_url': '/my/employee/discuss/channel/%s' % member.channel_id.id,
            }
        }

    @http.route('/employee_portal/discuss/call/decline', type='json', auth='user', csrf=False)
    def employee_discuss_call_decline(self, channel_id=None):
        """Decline only the current employee's native RTC invitation."""
        user = self._employee_user()
        if not user:
            return {'ok': False}
        try:
            channel_id = int(channel_id or 0)
        except (TypeError, ValueError):
            return {'ok': False}
        member = request.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', channel_id),
            ('partner_id', '=', user.partner_id.id),
            ('rtc_inviting_session_id', '!=', False),
        ], limit=1)
        if not member or not self._is_allowed_channel(member.channel_id, user):
            return {'ok': False}
        member.channel_id.sudo()._rtc_cancel_invitations(member_ids=member.ids)
        return {'ok': True}
