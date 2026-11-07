import base64
import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

CALL_RING_TIMEOUT_SECONDS = 45


class PortalCallController(http.Controller):
    """JSON-RPC signalling endpoints for calling between portal/internal users.

    Any active Odoo Portal user or Internal User can call any other active
    Portal/Internal user. There is no per-pair allow-list requirement.
    """

    def _user(self):
        return request.env.user

    def _get_session(self, uuid):
        session = request.env['portal.call.session'].sudo().search([('uuid', '=', uuid)], limit=1)
        if not session or not session._is_participant(self._user()):
            return None
        return session

    def _queue_signal(self, session, recipient, event, payload=None):
        request.env['portal.call.signal'].sudo().create({
            'session_id': session.id,
            'recipient_id': recipient.id,
            'event': event,
            'payload': json.dumps(payload or {}),
        })

    def _is_callable_user(self, user):
        """A callable target must be an active Odoo user linked to an active employee."""
        if not user or not user.active:
            return False
        return bool(request.env['hr.employee'].sudo().search_count([
            ('active', '=', True),
            ('user_id', '=', user.id),
        ]))

    @http.route('/employee_portal/call/avatar/<int:user_id>', type='http', auth='user', csrf=False)
    def call_avatar(self, user_id):
        """Serve employee avatars to authenticated users without exposing res.users read access."""
        employee = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '=', user_id), ('user_id.active', '=', True),
        ], limit=1)
        if not employee:
            return request.not_found()
        image = employee.image_128 or employee.user_id.partner_id.avatar_128
        if not image:
            return request.not_found()
        try:
            content = base64.b64decode(image)
        except Exception:
            return request.not_found()
        return request.make_response(content, headers=[
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'private, max-age=3600'),
        ])

    def _presence_map(self, user_ids):
        """Return lightweight call availability for employee users.

        Presence is intentionally separate from Odoo Discuss presence so it works
        identically for internal and portal employees. The browser sends a small
        heartbeat every 15 seconds while Odoo is open.
        """
        user_ids = [int(uid) for uid in user_ids if uid]
        if not user_ids:
            return {}

        now = fields.Datetime.now()
        online_before = fields.Datetime.subtract(now, seconds=90)
        active_before = fields.Datetime.subtract(now, minutes=2)

        Presence = request.env['portal.call.presence'].sudo()
        rows = Presence.search([('user_id', 'in', user_ids)])
        by_user = {row.user_id.id: row for row in rows}

        Session = request.env['portal.call.session'].sudo()
        busy_sessions = Session.search([
            ('state', 'in', ['ringing', 'ongoing']),
            ('active_participant_ids', 'in', user_ids),
        ])
        busy_ids = set(busy_sessions.mapped('active_participant_ids').ids) & set(user_ids)

        result = {}
        for uid in user_ids:
            row = by_user.get(uid)
            recently_seen = bool(row and row.last_seen and row.last_seen >= online_before)
            if uid in busy_ids and recently_seen:
                result[uid] = 'in_call'
            elif not recently_seen:
                result[uid] = 'offline'
            elif row.last_activity and row.last_activity >= active_before:
                result[uid] = 'online'
            else:
                result[uid] = 'away'
        return result

    @http.route('/employee_portal/call/presence', type='json', auth='user', csrf=False)
    def call_presence(self, active=False):
        """Heartbeat for Online/Away/Offline plus current In Call state."""
        user = self._user()
        if not self._is_callable_user(user):
            return {'ok': False, 'statuses': {}}

        Presence = request.env['portal.call.presence'].sudo()
        presence = Presence.search([('user_id', '=', user.id)], limit=1)
        now = fields.Datetime.now()
        vals = {'last_seen': now}
        if active:
            vals['last_activity'] = now
        if presence:
            presence.write(vals)
        else:
            vals['user_id'] = user.id
            # First heartbeat is an interaction with Odoo, so avoid showing Away
            # immediately if the client did not yet report an activity event.
            vals.setdefault('last_activity', now)
            Presence.create(vals)

        employees = request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
            ('user_id.active', '=', True),
        ])
        statuses = self._presence_map(employees.mapped('user_id').ids)
        return {
            'ok': True,
            'statuses': {str(uid): status for uid, status in statuses.items()},
        }

    # ------------------------------------------------------------------
    # Directory
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/contacts', type='json', auth='user', csrf=False)
    def call_contacts(self):
        user = self._user()

        # Build the directory from HR employees, not from res.users. This keeps
        # vendor/customer portal accounts out of the calling directory while
        # still supporting employees whose login type is Portal or Internal.
        employees = request.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('user_id', '!=', False),
            ('user_id.active', '=', True),
            ('user_id', '!=', user.id),
        ], order='name asc')

        presence = self._presence_map(employees.mapped('user_id').ids)
        result = []
        seen_user_ids = set()
        for employee in employees:
            contact = employee.user_id
            if not contact or contact.id in seen_user_ids:
                continue
            seen_user_ids.add(contact.id)
            is_portal = contact.has_group('base.group_portal')
            result.append({
                'user_id': contact.id,
                'name': employee.name or contact.name,
                'user_type': 'Portal Employee' if is_portal else 'Internal Employee',
                'department': employee.department_id.name or '',
                'note': employee.job_title or '',
                'avatar_url': '/employee_portal/call/avatar/%s' % contact.id,
                'presence': presence.get(contact.id, 'offline'),
            })
        return result

    # ------------------------------------------------------------------
    # Call lifecycle
    # ------------------------------------------------------------------
    def _notify_telegram_incoming(self, target, caller, is_group=False):
        """Best-effort Telegram alert using the portal's existing bot integration."""
        try:
            title = 'Incoming Odoo Group Call' if is_group else 'Incoming Odoo Call'
            body = '%s invited you to a group call.' % caller.name if is_group else '%s is calling you.' % caller.name
            request.env['employee.portal.telegram.service'].sudo().send_to_user(
                target, title, body + ' Open Odoo to answer.', path='/my/employee'
            )
        except Exception:
            _logger.exception('Could not send Telegram incoming-call notification to user %s', target.id)


    def _notify_telegram_missed(self, targets, caller, is_group=False):
        """Best-effort Telegram missed-call alert after a ringing call ends unanswered."""
        service = request.env['employee.portal.telegram.service'].sudo()
        title = 'Missed Odoo Group Call' if is_group else 'Missed Odoo Call'
        for target in targets:
            try:
                body = '%s called you and the call was not answered.' % (caller.name or 'Employee')
                service.send_to_user(target, title, body, path='/my/employee')
            except Exception:
                _logger.exception('Could not send Telegram missed-call notification to user %s', target.id)

    @http.route('/employee_portal/call/start', type='json', auth='user', csrf=False)
    def call_start(self, target_user_id=None, target_user_ids=None, call_type='audio'):
        user = self._user()
        raw_ids = list(target_user_ids or [])
        if target_user_id:
            raw_ids.append(target_user_id)

        target_ids = []
        for raw_id in raw_ids:
            try:
                uid = int(raw_id)
            except (TypeError, ValueError):
                continue
            if uid and uid != user.id and uid not in target_ids:
                target_ids.append(uid)

        targets = []
        for uid in target_ids:
            target = request.env['res.users'].sudo().browse(uid).exists()
            if target and self._is_callable_user(target):
                targets.append(target)
        if not targets:
            return {'error': 'invalid_target'}

        is_group = len(targets) > 1
        participant_ids = [user.id] + [target.id for target in targets]
        session = request.env['portal.call.session'].sudo().create({
            'caller_id': user.id,
            # callee_id is retained for backward compatibility with the model;
            # participant_ids is the authoritative membership for meetings.
            'callee_id': targets[0].id,
            'call_type': call_type if call_type in ('audio', 'video') else 'audio',
            'participant_ids': [(6, 0, participant_ids)],
            'active_participant_ids': [(6, 0, [user.id])],
            'joined_participant_ids': [(6, 0, [user.id])],
        })
        for target in targets:
            self._queue_signal(session, target, 'incoming', {
                'caller_id': user.id,
                'caller_name': user.name,
                'caller_avatar_url': '/employee_portal/call/avatar/%s' % user.id,
                'call_type': session.call_type,
                'meeting': is_group,
            })
            self._notify_telegram_incoming(target, user, is_group=is_group)
        return {'uuid': session.uuid, 'invited': [target.id for target in targets], 'meeting': is_group}

    @http.route('/employee_portal/call/accept', type='json', auth='user', csrf=False)
    def call_accept(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        session.write({
            'state': 'ongoing',
            'answered_date': session.answered_date or fields.Datetime.now(),
            'active_participant_ids': [(4, user.id)],
            'joined_participant_ids': [(4, user.id)],
        })
        for other in session.active_participant_ids.filtered(lambda u: u.id != user.id):
            self._queue_signal(session, other, 'accepted', {'user_id': user.id, 'user_name': user.name})
        return {'ok': True}

    @http.route('/employee_portal/call/reject', type='json', auth='user', csrf=False)
    def call_reject(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        is_group = len(session.participant_ids) > 2
        if session.state == 'ongoing' or is_group:
            # In a meeting, one invitee declining/leaving must never terminate
            # the session for everyone else. Remove only that participant.
            session.write({
                'active_participant_ids': [(3, user.id)],
                # Keep participant_ids as the permanent invitation roster so
                # Recent Calls can still show who was invited after the meeting.
                'declined_participant_ids': [(4, user.id)],
            })
            for other in session.active_participant_ids:
                self._queue_signal(session, other, 'participant_left', {
                    'user_id': user.id, 'user_name': user.name, 'declined': session.state == 'ringing'
                })
            if len(session.participant_ids) < 2:
                session.write({'state': 'ended' if session.answered_date else 'missed', 'end_date': fields.Datetime.now()})
        else:
            session.write({
                'state': 'rejected',
                'end_date': fields.Datetime.now(),
                'declined_participant_ids': [(4, user.id)],
            })
            other = session._other_party(user)
            self._queue_signal(session, other, 'rejected', {'user_id': user.id})
        return {'ok': True}

    @http.route('/employee_portal/call/end', type='json', auth='user', csrf=False)
    def call_end(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        was_ringing = session.state == 'ringing' and not session.answered_date
        session.write({'active_participant_ids': [(3, user.id)]})
        remaining = session.active_participant_ids

        # If the caller cancels while the call is still ringing, invitees have
        # not joined active_participant_ids yet. Notify the permanent invitation
        # roster so every incoming popup/ringtone is dismissed immediately.
        if was_ringing and user.id == session.caller_id.id:
            invitees = session.participant_ids.filtered(lambda u: u.id != user.id)
            session.write({'state': 'missed', 'end_date': fields.Datetime.now()})
            for other in invitees:
                self._queue_signal(session, other, 'cancelled', {'user_id': user.id})
            self._notify_telegram_missed(invitees, user, is_group=len(session.participant_ids) > 2)
            return {'ok': True}

        for other in remaining:
            self._queue_signal(session, other, 'participant_left', {'user_id': user.id, 'user_name': user.name})
        if len(remaining) < 2:
            session.write({'state': 'ended' if session.answered_date else 'missed', 'end_date': fields.Datetime.now()})
            for other in remaining:
                self._queue_signal(session, other, 'ended', {})
        return {'ok': True}

    @http.route('/employee_portal/call/add_participants', type='json', auth='user', csrf=False)
    def call_add_participants(self, uuid, user_ids):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        added = []
        inviter = self._user()
        for uid in set(int(x) for x in (user_ids or [])):
            target = request.env['res.users'].sudo().browse(uid).exists()
            if not target or target.id == inviter.id or target.id in session.participant_ids.ids or not self._is_callable_user(target):
                continue
            session.write({'participant_ids': [(4, target.id)]})
            self._queue_signal(session, target, 'incoming', {
                'caller_id': inviter.id, 'caller_name': inviter.name, 'caller_avatar_url': '/employee_portal/call/avatar/%s' % inviter.id, 'call_type': session.call_type, 'meeting': True,
            })
            self._notify_telegram_incoming(target, inviter, is_group=True)
            added.append(target.id)
        return {'ok': True, 'added': added}


    @http.route('/employee_portal/call/participants', type='json', auth='user', csrf=False)
    def call_participants(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session', 'participants': []}
        current = self._user()
        active_ids = set(session.active_participant_ids.ids)
        participants = []
        for user in session.participant_ids.sorted(key=lambda u: (u.name or '').lower()):
            participants.append({
                'user_id': user.id,
                'name': user.name or 'Employee',
                'active': user.id in active_ids,
                'is_self': user.id == current.id,
                'avatar_url': '/employee_portal/call/avatar/%s' % user.id,
            })
        return {'participants': participants}

    @http.route('/employee_portal/call/signal', type='json', auth='user', csrf=False)
    def call_signal(self, uuid, signal_type, data):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        sender = self._user()
        target_user_id = int((data or {}).get('_target_user_id') or 0) if isinstance(data, dict) else 0
        clean_data = dict(data or {}) if isinstance(data, dict) else data
        if isinstance(clean_data, dict):
            clean_data.pop('_target_user_id', None)
        targets = session.active_participant_ids.filtered(lambda u: u.id != sender.id and (not target_user_id or u.id == target_user_id))
        for other in targets:
            self._queue_signal(session, other, 'signal', {'signal_type': signal_type, 'data': clean_data, 'sender_id': sender.id, 'sender_name': sender.name})
        return {'ok': True}

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/poll', type='json', auth='user', csrf=False)
    def call_poll(self, last_id=0):
        user = self._user()
        Session = request.env['portal.call.session'].sudo()
        Signal = request.env['portal.call.signal'].sudo()

        # A ringing call is temporary. If nobody answers within the timeout,
        # close it as missed so an abandoned browser/tab can never leave a
        # permanent "Incoming call" popup behind.
        stale_before = fields.Datetime.subtract(
            fields.Datetime.now(), seconds=CALL_RING_TIMEOUT_SECONDS
        )
        stale_sessions = Session.search([
            ('state', '=', 'ringing'),
            ('start_date', '<', stale_before),
            '|',
            ('caller_id', '=', user.id),
            ('callee_id', '=', user.id),
        ])
        for session in stale_sessions:
            # Writing state first prevents the other participant's poll from
            # expiring and signalling the same session a second time.
            session.write({
                'state': 'missed',
                'end_date': fields.Datetime.now(),
            })
            other = session._other_party(user)
            self._queue_signal(session, other, 'cancelled', {})
            invitees = session.participant_ids.filtered(lambda u: u.id != session.caller_id.id)
            self._notify_telegram_missed(invitees, session.caller_id, is_group=len(session.participant_ids) > 2)

        # Only unread mailbox rows are returned. Previously consumed=True rows
        # were still fetched whenever a page reloaded with last_id=0, which
        # replayed old incoming calls indefinitely.
        signals = Signal.search([
            ('recipient_id', '=', user.id),
            ('consumed', '=', False),
            ('id', '>', int(last_id or 0)),
        ], order='id asc', limit=50)
        result = []
        max_id = int(last_id or 0)
        for s in signals:
            max_id = max(max_id, s.id)
            session = s.session_id

            # Never resurrect an incoming event for a call that is no longer
            # ringing (missed/rejected/ended).
            if s.event == 'incoming' and session.state not in ('ringing', 'ongoing'):
                continue
            if s.event == 'accepted' and session.state != 'ongoing':
                continue
            if s.event == 'signal' and session.state not in ('ringing', 'ongoing'):
                continue

            try:
                payload = json.loads(s.payload or '{}')
            except ValueError:
                payload = {}
            result.append({
                'id': s.id,
                'uuid': session.uuid,
                'event': s.event,
                'payload': payload,
            })
        if signals:
            signals.write({'consumed': True})
        return {'last_id': max_id, 'events': result}

    # ------------------------------------------------------------------
    # Recent calls / missed calls
    # ------------------------------------------------------------------
    def _history_status_for_user(self, session, user):
        """Return the user's own view of a session status."""
        if user.id == session.caller_id.id:
            if session.state == 'ringing':
                return 'ringing'
            if session.state == 'rejected':
                return 'declined'
            if session.state == 'missed' and not session.answered_date:
                return 'no_answer'
            if session.state == 'ongoing':
                return 'ongoing'
            return 'completed' if session.answered_date else 'no_answer'

        if user.id in session.declined_participant_ids.ids:
            return 'declined'
        if user.id in session.joined_participant_ids.ids:
            return 'ongoing' if session.state == 'ongoing' else 'completed'
        if session.state in ('ended', 'missed', 'rejected'):
            return 'missed'
        return 'ringing'

    def _is_missed_for_user(self, session, user):
        return user.id != session.caller_id.id and self._history_status_for_user(session, user) == 'missed'

    @http.route('/employee_portal/call/history', type='json', auth='user', csrf=False)
    def call_history(self, limit=40):
        user = self._user()
        if not self._is_callable_user(user):
            return {'calls': [], 'unread_missed_count': 0}
        try:
            limit = max(1, min(int(limit or 40), 100))
        except (TypeError, ValueError):
            limit = 40

        Session = request.env['portal.call.session'].sudo()
        sessions = Session.search([
            '|', '|',
            ('participant_ids', 'in', user.id),
            ('caller_id', '=', user.id),
            ('callee_id', '=', user.id),
        ], order='start_date desc, id desc', limit=limit)

        rows = []
        unread_missed = 0
        now = fields.Datetime.now()
        for session in sessions:
            # Older sessions created before participant history fields existed
            # still remain readable through caller/callee.
            participants = session.participant_ids
            if not participants:
                participants = session.caller_id | session.callee_id
            other_users = participants.filtered(lambda u: u.id != user.id)
            status = self._history_status_for_user(session, user)
            missed = status == 'missed'
            seen = user.id in session.missed_seen_user_ids.ids
            if missed and not seen:
                unread_missed += 1

            is_group = len(participants) > 2
            other_names = [u.name or 'Employee' for u in other_users]
            if is_group:
                if other_names:
                    title = other_names[0] + ((' + %s others' % (len(other_names) - 1)) if len(other_names) > 1 else '')
                else:
                    title = 'Group call'
            else:
                title = other_names[0] if other_names else (session.caller_id.name or 'Employee')

            end = session.end_date or (now if session.state == 'ongoing' else None)
            duration = 0
            if session.answered_date and end:
                duration = max(0, int((end - session.answered_date).total_seconds()))

            rows.append({
                'uuid': session.uuid,
                'direction': 'outgoing' if session.caller_id.id == user.id else 'incoming',
                'status': status,
                'missed_unread': bool(missed and not seen),
                'is_group': is_group,
                'title': title,
                'started_at': fields.Datetime.to_string(session.start_date) if session.start_date else '',
                'duration_seconds': duration,
                'callback_user_ids': other_users.ids,
                'avatar_url': ('/employee_portal/call/avatar/%s' % other_users[0].id) if len(other_users) == 1 else '',
            })
        return {'calls': rows, 'unread_missed_count': unread_missed}

    @http.route('/employee_portal/call/history/mark_seen', type='json', auth='user', csrf=False)
    def call_history_mark_seen(self):
        user = self._user()
        if not self._is_callable_user(user):
            return {'ok': False}
        Session = request.env['portal.call.session'].sudo()
        sessions = Session.search([
            '|', '|',
            ('participant_ids', 'in', user.id),
            ('caller_id', '=', user.id),
            ('callee_id', '=', user.id),
            ('state', 'in', ['ended', 'missed', 'rejected']),
        ])
        for session in sessions:
            if self._is_missed_for_user(session, user) and user.id not in session.missed_seen_user_ids.ids:
                session.write({'missed_seen_user_ids': [(4, user.id)]})
        return {'ok': True}

    # ------------------------------------------------------------------
    # ICE servers
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/ice_servers', type='json', auth='user', csrf=False)
    def ice_servers(self):
        ICP = request.env['ir.config_parameter'].sudo()
        servers = [{'urls': ['stun:stun.l.google.com:19302']}]
        turn_url = ICP.get_param('employee_portal_suite.turn_url')
        if turn_url:
            entry = {'urls': [turn_url]}
            username = ICP.get_param('employee_portal_suite.turn_username')
            credential = ICP.get_param('employee_portal_suite.turn_credential')
            if username:
                entry['username'] = username
            if credential:
                entry['credential'] = credential
            servers.append(entry)
        return {'iceServers': servers}
