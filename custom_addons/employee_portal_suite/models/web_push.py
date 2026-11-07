import base64
import json
import logging
import os
import struct
import time
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=') .decode('ascii')


def _b64url_decode(value):
    if isinstance(value, str):
        value = value.encode('ascii')
    return base64.urlsafe_b64decode(value + b'=' * (-len(value) % 4))


def _hkdf_expand(prk, info, length):
    """RFC 5869 HKDF-Expand using SHA-256."""
    output = b''
    block = b''
    counter = 1
    while len(output) < length:
        hm = hmac.HMAC(prk, hashes.SHA256())
        hm.update(block + info + bytes([counter]))
        block = hm.finalize()
        output += block
        counter += 1
    return output[:length]


def _hmac_sha256(key, data):
    hm = hmac.HMAC(key, hashes.SHA256())
    hm.update(data)
    return hm.finalize()


class EmployeePortalPushSubscription(models.Model):
    _name = 'employee.portal.push.subscription'
    _description = 'Employee Portal Web Push Subscription'
    _order = 'write_date desc, id desc'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    endpoint = fields.Text(required=True, index=True)
    p256dh = fields.Text(required=True)
    auth = fields.Text(required=True)
    active = fields.Boolean(default=True, index=True)
    user_agent = fields.Text()
    device_label = fields.Char()
    last_success_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    _sql_constraints = [
        ('employee_portal_push_endpoint_uniq', 'unique(endpoint)', 'This push subscription is already registered.'),
    ]

    @api.model
    def register_subscription(self, user, subscription, user_agent=None, device_label=None):
        endpoint = (subscription or {}).get('endpoint') or ''
        keys = (subscription or {}).get('keys') or {}
        p256dh = keys.get('p256dh') or ''
        auth = keys.get('auth') or ''
        if not endpoint.startswith('https://') or not p256dh or not auth:
            return False
        # Validate key material now so malformed browser/client input never reaches
        # the notification path later.
        try:
            public_key = _b64url_decode(p256dh)
            auth_secret = _b64url_decode(auth)
            if len(public_key) != 65 or public_key[0] != 4 or len(auth_secret) < 16:
                return False
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_key)
        except Exception:
            return False

        existing = self.sudo().search([('endpoint', '=', endpoint)], limit=1)
        vals = {
            'user_id': user.id,
            'p256dh': p256dh,
            'auth': auth,
            'active': True,
            'user_agent': (user_agent or '')[:1000],
            'device_label': (device_label or '')[:128],
            'last_error': False,
        }
        if existing:
            existing.write(vals)
            return existing
        vals['endpoint'] = endpoint
        return self.sudo().create(vals)


class EmployeePortalWebPushService(models.AbstractModel):
    _name = 'employee.portal.webpush.service'
    _description = 'Employee Portal Web Push Service'

    _PRIVATE_PARAM = 'employee_portal.webpush_vapid_private'
    _PUBLIC_PARAM = 'employee_portal.webpush_vapid_public'

    def _ensure_vapid_keys(self):
        params = self.env['ir.config_parameter'].sudo()
        private_b64 = params.get_param(self._PRIVATE_PARAM)
        public_b64 = params.get_param(self._PUBLIC_PARAM)
        if private_b64 and public_b64:
            try:
                private_value = int.from_bytes(_b64url_decode(private_b64), 'big')
                private_key = ec.derive_private_key(private_value, ec.SECP256R1())
                return private_key, public_b64
            except Exception:
                _logger.warning('Stored Web Push VAPID key is invalid; generating a replacement.')

        private_key = ec.generate_private_key(ec.SECP256R1())
        private_value = private_key.private_numbers().private_value.to_bytes(32, 'big')
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        private_b64 = _b64url_encode(private_value)
        public_b64 = _b64url_encode(public_bytes)
        params.set_param(self._PRIVATE_PARAM, private_b64)
        params.set_param(self._PUBLIC_PARAM, public_b64)
        return private_key, public_b64

    def get_public_key(self):
        return self._ensure_vapid_keys()[1]

    def _vapid_token(self, endpoint, private_key, public_b64):
        parsed = urlsplit(endpoint)
        audience = '%s://%s' % (parsed.scheme, parsed.netloc)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        subject = base_url if base_url.startswith('https://') else 'mailto:webpush@localhost.invalid'
        header = {'typ': 'JWT', 'alg': 'ES256'}
        claims = {
            'aud': audience,
            'exp': int(time.time()) + (12 * 60 * 60),
            'sub': subject,
        }
        enc_header = _b64url_encode(json.dumps(header, separators=(',', ':')).encode())
        enc_claims = _b64url_encode(json.dumps(claims, separators=(',', ':')).encode())
        signing_input = ('%s.%s' % (enc_header, enc_claims)).encode('ascii')
        der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        raw_signature = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        token = '%s.%s.%s' % (enc_header, enc_claims, _b64url_encode(raw_signature))
        return 'vapid t=%s, k=%s' % (token, public_b64)

    def _encrypt_payload(self, payload, subscription):
        client_public = _b64url_decode(subscription.p256dh)
        auth_secret = _b64url_decode(subscription.auth)
        client_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), client_public)

        server_private = ec.generate_private_key(ec.SECP256R1())
        server_public = server_private.public_key().public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        shared_secret = server_private.exchange(ec.ECDH(), client_key)

        # RFC 8291: authenticate the ECDH secret first, then derive the content key.
        prk_key = _hmac_sha256(auth_secret, shared_secret)
        key_info = b'WebPush: info\x00' + client_public + server_public
        ikm = _hkdf_expand(prk_key, key_info, 32)

        salt = os.urandom(16)
        prk = _hmac_sha256(salt, ikm)
        cek = _hkdf_expand(prk, b'Content-Encoding: aes128gcm\x00', 16)
        nonce = _hkdf_expand(prk, b'Content-Encoding: nonce\x00', 12)

        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        # aes128gcm records end with delimiter 0x02 when there is no padding.
        plaintext = raw_payload + b'\x02'
        ciphertext = AESGCM(cek).encrypt(nonce, plaintext, None)
        record_size = 4096
        return salt + struct.pack('!I', record_size) + bytes([len(server_public)]) + server_public + ciphertext

    def _send_subscription(self, subscription, payload, urgency='normal'):
        private_key, public_b64 = self._ensure_vapid_keys()
        try:
            body = self._encrypt_payload(payload, subscription)
            headers = {
                'Authorization': self._vapid_token(subscription.endpoint, private_key, public_b64),
                'Content-Encoding': 'aes128gcm',
                'Content-Type': 'application/octet-stream',
                'TTL': '86400',
                'Urgency': urgency if urgency in ('very-low', 'low', 'normal', 'high') else 'normal',
            }
            response = requests.post(subscription.endpoint, data=body, headers=headers, timeout=4)
            if response.status_code in (200, 201, 202):
                subscription.sudo().write({'last_success_at': fields.Datetime.now(), 'last_error': False})
                return True
            if response.status_code in (404, 410):
                subscription.sudo().write({
                    'active': False,
                    'last_error': 'Push endpoint expired (%s)' % response.status_code,
                })
                return False
            error = 'Push service returned HTTP %s: %s' % (response.status_code, (response.text or '')[:500])
            subscription.sudo().write({'last_error': error})
            _logger.warning('%s', error)
            return False
        except Exception as exc:
            subscription.sudo().write({'last_error': str(exc)[:1000]})
            _logger.exception('Web Push delivery failed for subscription %s', subscription.id)
            return False

    def _url_for_user(self, user, path=None):
        """Return a destination appropriate for the recipient's account type.

        Portal/share employees use the Employee Portal. Internal users stay in the
        Odoo backend even if the original notification was raised by a portal flow.
        """
        path = path or '/my/employee'
        if not user or user.share or path.startswith(('http://', 'https://')):
            return path

        import re
        if path.startswith('/my/employee/discuss'):
            return '/odoo/discuss'

        match = re.match(r'^/my/employee/(?:approvals|requests)/(\d+)', path)
        if match:
            return '/web#id=%s&model=employee.request&view_type=form' % match.group(1)

        match = re.match(r'^/my/employee/material(?:/approvals)?/(\d+)', path)
        if match:
            return '/web#id=%s&model=material.request&view_type=form' % match.group(1)

        # Portal-only pages (attendance, reports, sign, profile, etc.) do not have
        # a universal one-to-one backend URL. Keep internal users in /web rather
        # than ever dropping them into /my/employee.
        if path.startswith('/my/employee'):
            return '/web'
        return path

    def send_to_user(self, user, title, body, path=None, kind='message', tag=None, urgency=None):
        if not user or not user.active:
            return False
        subscriptions = self.env['employee.portal.push.subscription'].sudo().search([
            ('user_id', '=', user.id), ('active', '=', True),
        ])
        if not subscriptions:
            return False
        payload = {
            'title': str(title or 'ABSAR Employee'),
            'body': str(body or ''),
            'url': self._url_for_user(user, path),
            'kind': kind or 'message',
            'tag': tag or ('employee-portal-%s' % (kind or 'message')),
            'icon': '/employee_portal_suite/static/icons/portal-192.png',
            'badge': '/employee_portal_suite/static/icons/portal-64.png',
        }
        urgency = urgency or ('high' if kind in ('call', 'video_call') else 'normal')
        delivered = False
        for subscription in subscriptions:
            delivered = self._send_subscription(subscription, payload, urgency=urgency) or delivered
        return delivered
