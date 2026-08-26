import json
import logging

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PortalCallController(http.Controller):
    """JSON-RPC signalling endpoints for the portal <-> internal calling feature.

    Design notes:
    - auth='user' means both portal and internal users can call these (portal
      users ARE res.users records with the portal group).
    - csrf=False: these are pure JSON-RPC actions gated entirely by session
      auth + explicit ownership checks below (never by model ACLs alone),
      so CSRF token exchange isn't needed. Every mutating action re-checks
      that the caller is an actual participant of the session/contact.
    - Signalling is a polled queue (portal.call.signal), not the mail bus,
      so this has zero dependency on Discuss/RTC internals and behaves
      identically on frontend and backend. Expect ~1-2s of added latency
      on ringing/offer/answer exchange; the media itself is peer-to-peer
      WebRTC once connected and is not affected by polling speed.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

    def _is_allowed_pair(self, user_a, user_b):
        Contact = request.env['portal.call.contact'].sudo()
        return bool(Contact.search([
            '|',
            '&', ('portal_user_id', '=', user_a.id), ('internal_user_id', '=', user_b.id),
            '&', ('portal_user_id', '=', user_b.id), ('internal_user_id', '=', user_a.id),
        ], limit=1))

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/contacts', type='json', auth='user', csrf=False)
    def call_contacts(self):
        user = self._user()
        Contact = request.env['portal.call.contact'].sudo()
        if user.has_group('employee_portal_suite.group_employee_portal'):
            contacts = Contact.search([('portal_user_id', '=', user.id)])
            return [{
                'user_id': c.internal_user_id.id,
                'name': c.internal_user_id.name,
                'note': c.note or '',
            } for c in contacts]
        else:
            contacts = Contact.search([('internal_user_id', '=', user.id)])
            return [{
                'user_id': c.portal_user_id.id,
                'name': c.portal_user_id.name,
                'note': c.note or '',
            } for c in contacts]

    # ------------------------------------------------------------------
    # Call lifecycle
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/start', type='json', auth='user', csrf=False)
    def call_start(self, target_user_id, call_type='audio'):
        user = self._user()
        target = request.env['res.users'].sudo().browse(int(target_user_id)).exists()
        if not target or target.id == user.id:
            return {'error': 'invalid_target'}
        if not self._is_allowed_pair(user, target):
            return {'error': 'not_allowed'}

        session = request.env['portal.call.session'].sudo().create({
            'caller_id': user.id,
            'callee_id': target.id,
            'call_type': call_type if call_type in ('audio', 'video') else 'audio',
        })
        self._queue_signal(session, target, 'incoming', {
            'caller_id': user.id,
            'caller_name': user.name,
            'call_type': session.call_type,
        })
        return {'uuid': session.uuid}

    @http.route('/employee_portal/call/accept', type='json', auth='user', csrf=False)
    def call_accept(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state != 'ringing':
            return {'error': 'invalid_session'}
        session.write({'state': 'ongoing', 'answered_date': fields.Datetime.now()})
        other = session._other_party(self._user())
        self._queue_signal(session, other, 'accepted', {})
        return {'ok': True}

    @http.route('/employee_portal/call/reject', type='json', auth='user', csrf=False)
    def call_reject(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state != 'ringing':
            return {'error': 'invalid_session'}
        session.write({'state': 'rejected', 'end_date': fields.Datetime.now()})
        other = session._other_party(self._user())
        self._queue_signal(session, other, 'rejected', {})
        return {'ok': True}

    @http.route('/employee_portal/call/end', type='json', auth='user', csrf=False)
    def call_end(self, uuid):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        new_state = 'ended' if session.state == 'ongoing' else 'missed'
        session.write({'state': new_state, 'end_date': fields.Datetime.now()})
        other = session._other_party(self._user())
        self._queue_signal(session, other, 'ended' if new_state == 'ended' else 'cancelled', {})
        return {'ok': True}

    @http.route('/employee_portal/call/signal', type='json', auth='user', csrf=False)
    def call_signal(self, uuid, signal_type, data):
        session = self._get_session(uuid)
        if not session or session.state not in ('ringing', 'ongoing'):
            return {'error': 'invalid_session'}
        other = session._other_party(self._user())
        self._queue_signal(session, other, 'signal', {'signal_type': signal_type, 'data': data})
        return {'ok': True}

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    @http.route('/employee_portal/call/poll', type='json', auth='user', csrf=False)
    def call_poll(self, last_id=0):
        user = self._user()
        Signal = request.env['portal.call.signal'].sudo()
        signals = Signal.search([
            ('recipient_id', '=', user.id),
            ('id', '>', int(last_id or 0)),
        ], order='id asc', limit=50)
        result = []
        max_id = int(last_id or 0)
        for s in signals:
            max_id = max(max_id, s.id)
            try:
                payload = json.loads(s.payload or '{}')
            except ValueError:
                payload = {}
            result.append({
                'id': s.id,
                'uuid': s.session_id.uuid,
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
