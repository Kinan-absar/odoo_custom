# -*- coding: utf-8 -*-
import base64
import json
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
except ImportError:  # pragma: no cover
    ec = None
    serialization = None

try:
    from pywebpush import webpush, WebPushException
except ImportError:  # pragma: no cover
    webpush = None
    WebPushException = Exception


def _b64url(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b'=').decode('ascii')


class PortalPushSubscription(models.Model):
    _name = 'portal.push.subscription'
    _description = 'Web Push Subscription (Portal / Backend User Device)'
    _rec_name = 'endpoint'

    user_id = fields.Many2one(
        'res.users', string='User', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user.id,
    )
    endpoint = fields.Char(string='Push Endpoint', required=True)
    p256dh = fields.Char(string='P256DH Key', required=True)
    auth_key = fields.Char(string='Auth Key', required=True)
    user_agent = fields.Char(string='Device / Browser')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('endpoint_unique', 'unique(endpoint)', 'This device is already subscribed.'),
    ]

    # ------------------------------------------------------------------
    # SUBSCRIBE / UNSUBSCRIBE (called from the portal controller)
    # ------------------------------------------------------------------
    @api.model
    def _register_subscription(self, user, subscription_info, user_agent=None):
        endpoint = subscription_info.get('endpoint')
        keys = subscription_info.get('keys') or {}
        p256dh = keys.get('p256dh')
        auth_key = keys.get('auth')
        if not (endpoint and p256dh and auth_key):
            return False

        existing = self.sudo().search([('endpoint', '=', endpoint)], limit=1)
        vals = {
            'user_id': user.id,
            'endpoint': endpoint,
            'p256dh': p256dh,
            'auth_key': auth_key,
            'user_agent': user_agent,
            'active': True,
        }
        if existing:
            existing.write(vals)
        else:
            self.sudo().create(vals)
        return True

    @api.model
    def _unregister_subscription(self, endpoint):
        if not endpoint:
            return False
        subs = self.sudo().search([('endpoint', '=', endpoint)])
        subs.unlink()
        return True

    # ------------------------------------------------------------------
    # VAPID KEY MANAGEMENT
    # Keys are generated once and stored on ir.config_parameter so every
    # push we sign uses the same identity.
    # ------------------------------------------------------------------
    @api.model
    def _get_vapid_keys(self):
        icp = self.env['ir.config_parameter'].sudo()
        private_b64 = icp.get_param('employee_portal_suite.vapid_private_key')
        public_b64 = icp.get_param('employee_portal_suite.vapid_public_key')

        if private_b64 and public_b64:
            return private_b64, public_b64

        if ec is None:
            _logger.warning(
                "Web Push: the 'cryptography' python package is not installed; "
                "cannot generate VAPID keys."
            )
            return False, False

        private_key = ec.generate_private_key(ec.SECP256R1())
        private_numbers = private_key.private_numbers()
        private_raw = private_numbers.private_value.to_bytes(32, 'big')
        public_raw = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

        private_b64 = _b64url(private_raw)
        public_b64 = _b64url(public_raw)

        icp.set_param('employee_portal_suite.vapid_private_key', private_b64)
        icp.set_param('employee_portal_suite.vapid_public_key', public_b64)
        return private_b64, public_b64

    @api.model
    def _get_vapid_public_key(self):
        _private, public_b64 = self._get_vapid_keys()
        return public_b64 or ''

    # ------------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------------
    @api.model
    def _send_push_to_users(self, users, title, body, url=None, tag=None):
        """Send a web push notification to every subscribed device of `users`.

        Silently does nothing if pywebpush/cryptography are not installed,
        if VAPID keys can't be generated, or if a user has no active
        subscription — this must never block the calling business flow.
        """
        if not users:
            return
        if webpush is None:
            _logger.warning(
                "Web Push: the 'pywebpush' python package is not installed; "
                "skipping push notification '%s'.", title
            )
            return

        private_b64, _public_b64 = self._get_vapid_keys()
        if not private_b64:
            return

        subscriptions = self.sudo().search([
            ('user_id', 'in', users.ids),
            ('active', '=', True),
        ])
        if not subscriptions:
            return

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url or (base_url + '/my/employee'),
            'tag': tag or 'employee-portal-suite',
        })

        vapid_claims = {
            'sub': 'mailto:%s' % (self.env.company.email or 'admin@example.com'),
        }

        for sub in subscriptions:
            subscription_info = {
                'endpoint': sub.endpoint,
                'keys': {
                    'p256dh': sub.p256dh,
                    'auth': sub.auth_key,
                },
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=private_b64,
                    vapid_claims=dict(vapid_claims),
                )
            except WebPushException as e:
                status_code = getattr(getattr(e, 'response', None), 'status_code', None)
                if status_code in (404, 410):
                    # Subscription expired or was revoked by the browser.
                    sub.unlink()
                else:
                    _logger.warning("Web Push: failed to send to %s: %s", sub.endpoint, e)
            except Exception:
                _logger.exception("Web Push: unexpected error sending to %s", sub.endpoint)
