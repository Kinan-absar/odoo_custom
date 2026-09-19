import json

from odoo import http
from odoo.http import request


class EmployeePortalWebPushController(http.Controller):

    def _employee_user(self):
        user = request.env.user
        if user._is_public() or not user.active:
            return False
        employee = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '=', user.id),
        ], limit=1)
        if not employee or user.has_group('employee_portal_suite.group_attendance_only'):
            return False
        return user

    def _json_response(self, payload, status=200):
        return request.make_response(
            json.dumps(payload),
            status=status,
            headers=[
                ('Content-Type', 'application/json; charset=utf-8'),
                ('Cache-Control', 'no-store'),
            ],
        )

    @http.route('/employee_portal/push/config', type='http', auth='user', methods=['GET'], csrf=False)
    def push_config(self, **kwargs):
        user = self._employee_user()
        if not user:
            return self._json_response({'ok': False, 'error': 'Employee access required.'}, status=403)
        public_key = request.env['employee.portal.webpush.service'].sudo().get_public_key()
        active = request.env['employee.portal.push.subscription'].sudo().search_count([
            ('user_id', '=', user.id), ('active', '=', True),
        ])
        return self._json_response({'ok': True, 'public_key': public_key, 'active_subscriptions': active})

    @http.route('/employee_portal/push/subscribe', type='http', auth='user', methods=['POST'], csrf=False)
    def push_subscribe(self, **kwargs):
        user = self._employee_user()
        if not user:
            return self._json_response({'ok': False, 'error': 'Employee access required.'}, status=403)
        try:
            data = request.httprequest.get_json(silent=True) or {}
        except Exception:
            data = {}
        subscription = data.get('subscription') or {}
        rec = request.env['employee.portal.push.subscription'].sudo().register_subscription(
            user,
            subscription,
            user_agent=request.httprequest.headers.get('User-Agent'),
            device_label=data.get('device_label'),
        )
        if not rec:
            return self._json_response({'ok': False, 'error': 'Invalid push subscription.'}, status=400)
        return self._json_response({'ok': True})

    @http.route('/employee_portal/push/unsubscribe', type='http', auth='user', methods=['POST'], csrf=False)
    def push_unsubscribe(self, **kwargs):
        user = self._employee_user()
        if not user:
            return self._json_response({'ok': False, 'error': 'Employee access required.'}, status=403)
        try:
            data = request.httprequest.get_json(silent=True) or {}
        except Exception:
            data = {}
        endpoint = (data.get('endpoint') or '').strip()
        domain = [('user_id', '=', user.id)]
        if endpoint:
            domain.append(('endpoint', '=', endpoint))
        request.env['employee.portal.push.subscription'].sudo().search(domain).write({'active': False})
        return self._json_response({'ok': True})

    @http.route('/employee_portal/push/test', type='http', auth='user', methods=['POST'], csrf=False)
    def push_test(self, **kwargs):
        user = self._employee_user()
        if not user:
            return self._json_response({'ok': False, 'error': 'Employee access required.'}, status=403)
        delivered = request.env['employee.portal.webpush.service'].sudo().send_to_user(
            user,
            'Employee Portal notifications enabled',
            'Push notifications are working on this device.',
            path='/my/employee',
            kind='test',
            tag='employee-portal-test',
            urgency='normal',
        )
        return self._json_response({'ok': True, 'delivered': bool(delivered)})
