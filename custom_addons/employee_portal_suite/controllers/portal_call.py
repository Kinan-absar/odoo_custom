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
                'avatar_url': f'/web/image/res.users/{contact.id}/avatar_128',
            })
        return result

    # ------------------------------------------------------------------
    # Call lifecycle
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/start', type='json', auth='user', csrf=False)
    def call_start(self, target_user_id, call_type='audio'):
        user = self._user()
        target = request.env['res.users'].sudo().browse(int(target_user_id)).exists()
        if not target or target.id == user.id:
            return {'error': 'invalid_target'}
        if not self._is_callable_user(target):
            return {'error': 'not_callable'}

        session = request.env['portal.call.session'].sudo().create({
            'caller_id': user.id,
            'callee_id': target.id,
            'call_type': call_type if call_type in ('audio', 'video') else 'audio',
            'participant_ids': [(6, 0, [user.id, target.id])],
            'active_participant_ids': [(6, 0, [user.id])],
        })
        self._queue_signal(session, target, 'incoming', {
            'caller_id': user.id,
            'caller_name': user.name,
            'call_type': session.call_type,
            'avatar_url': f'/web/image/res.users/{user.id}/avatar_128',
        })
        return {'uuid': session.uuid}

    @http.route('/employee_portal/call/accept', type='json', auth='user', csrf=False)
    def call_accept(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        session.write({'state': 'ongoing', 'answered_date': session.answered_date or fields.Datetime.now(), 'active_participant_ids': [(4, user.id)]})
        for other in session.active_participant_ids.filtered(lambda u: u.id != user.id):
            self._queue_signal(session, other, 'accepted', {'user_id': user.id, 'user_name': user.name})
        return {'ok': True}

    @http.route('/employee_portal/call/reject', type='json', auth='user', csrf=False)
    def call_reject(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        if session.state == 'ongoing':
            session.write({'active_participant_ids': [(3, user.id)]})
            for other in session.active_participant_ids:
                self._queue_signal(session, other, 'participant_left', {'user_id': user.id, 'user_name': user.name})
        else:
            session.write({'state': 'rejected', 'end_date': fields.Datetime.now()})
            other = session._other_party(user)
            self._queue_signal(session, other, 'rejected', {'user_id': user.id})
        return {'ok': True}

    @http.route('/employee_portal/call/end', type='json', auth='user', csrf=False)
    def call_end(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        user = self._user()
        session.write({'active_participant_ids': [(3, user.id)]})
        remaining = session.active_participant_ids
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
                'caller_id': inviter.id, 'caller_name': inviter.name, 'call_type': session.call_type, 'meeting': True,
                'avatar_url': f'/web/image/res.users/{inviter.id}/avatar_128',
            })
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
                'avatar_url': f'/web/image/res.users/{user.id}/avatar_128',
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
