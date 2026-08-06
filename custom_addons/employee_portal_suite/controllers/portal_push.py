# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request
from odoo.modules.module import get_module_resource


class PortalPushController(http.Controller):

    # ------------------------------------------------------------------
    # VAPID public key — the browser needs this to create a subscription
    # ------------------------------------------------------------------
    @http.route('/employee_portal_suite/push/vapid_public_key', type='http', auth='user', csrf=False)
    def push_vapid_public_key(self, **kw):
        key = request.env['portal.push.subscription'].sudo()._get_vapid_public_key()
        return request.make_response(
            json.dumps({'publicKey': key}),
            headers=[('Content-Type', 'application/json')],
        )

    # ------------------------------------------------------------------
    # SUBSCRIBE
    # ------------------------------------------------------------------
    @http.route('/employee_portal_suite/push/subscribe', type='json', auth='user', csrf=False)
    def push_subscribe(self, subscription=None, **kw):
        if not subscription:
            return {'ok': False, 'error': 'missing_subscription'}
        user_agent = request.httprequest.headers.get('User-Agent')
        ok = request.env['portal.push.subscription'].sudo()._register_subscription(
            request.env.user, subscription, user_agent=user_agent
        )
        return {'ok': ok}

    # ------------------------------------------------------------------
    # UNSUBSCRIBE
    # ------------------------------------------------------------------
    @http.route('/employee_portal_suite/push/unsubscribe', type='json', auth='user', csrf=False)
    def push_unsubscribe(self, endpoint=None, **kw):
        ok = request.env['portal.push.subscription'].sudo()._unregister_subscription(endpoint)
        return {'ok': ok}

    # ------------------------------------------------------------------
    # SERVICE WORKER
    # Served from the site root (not /static/...) so its scope covers the
    # whole portal — required by the Push API. auth='public' because the
    # browser fetches it before/without the session context being relevant.
    # ------------------------------------------------------------------
    @http.route('/push-sw.js', type='http', auth='public', csrf=False)
    def push_service_worker(self, **kw):
        js_path = get_module_resource(
            'employee_portal_suite', 'static', 'src', 'js', 'push_service_worker.js'
        )
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/javascript'),
                ('Service-Worker-Allowed', '/'),
                ('Cache-Control', 'no-cache'),
            ],
        )
