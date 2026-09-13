# -*- coding: utf-8 -*-
import json

from odoo import http, _
from odoo.http import request
from odoo.addons.mail.tools.discuss import Store
from odoo.addons.employee_portal_suite.controllers.portal_native_discuss import (
    EmployeePortalNativeDiscussController,
)


class AbsarChatPWAController(EmployeePortalNativeDiscussController):
    """Standalone PWA shell around the already-working native Employee Discuss.

    The hub is custom, but opening a conversation uses Odoo's real
    ``mail.discuss_public_channel_template`` and Store. This intentionally reuses
    Employee Portal Suite's filtering/security/channel creation helpers so Absar Chat
    and /my/employee/discuss remain the same communication system.
    """

    @http.route(['/chat', '/chat/'], type='http', auth='user', website=True, methods=['GET'])
    def absar_chat_home(self, **kwargs):
        user = self._employee_user()
        if not user:
            return request.render('absar_chat_pwa.access_denied_page', {
                'title': _('Access Restricted'),
                'message': _('Absar Chat is restricted to authorized company employees only.'),
            })

        channels = self._portal_channels(user)
        channel_rows = []
        for channel in channels:
            member = channel.channel_member_ids.filtered(
                lambda m: m.partner_id.id == user.partner_id.id
            )[:1]
            users = self._channel_users(channel)
            is_group = channel.channel_type == 'group' or len(users) > 2
            presence, presence_label = self._channel_presence(channel, user)
            channel_rows.append({
                'id': channel.id,
                'name': self._channel_label(channel, user),
                'avatar': self._channel_avatar(channel, user),
                'is_group': is_group,
                'presence': presence,
                'presence_label': presence_label,
                'unread': int(member.message_unread_counter or 0),
                'last_interest_dt': channel.last_interest_dt,
            })

        employee_rows = []
        for emp_user in self._employee_users().filtered(lambda u: u.id != user.id):
            presence, presence_label = self._discuss_presence(emp_user)
            employee_rows.append({
                'id': emp_user.id,
                'name': emp_user.name,
                'avatar': self._user_avatar(emp_user),
                'presence': presence,
                'presence_label': presence_label,
            })

        return request.render('absar_chat_pwa.chat_home', {
            'channels': channel_rows,
            'employees': employee_rows,
            'current_user': user,
            'current_avatar': self._user_avatar(user),
            'csrf_token': request.csrf_token(),
        })

    @http.route('/chat/start', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def absar_chat_start(self, participant_ids=None, group_name=None, **kwargs):
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
            return request.redirect('/chat/')
        return request.redirect('/chat/channel/%s' % channel.id)

    @http.route('/chat/channel/<int:channel_id>', type='http', auth='user', website=True, methods=['GET'])
    def absar_chat_channel(self, channel_id, **kwargs):
        user = self._employee_user()
        if not user:
            return request.redirect('/my/employee')

        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not self._is_allowed_channel(channel, user):
            return request.not_found()

        channel.sudo().write({'is_employee_portal_channel': True})
        channel_user = channel.with_user(user)
        store = Store()
        store.add({
            'companyName': request.env.company.name,
            'inPublicPage': True,
            'employeePortalDiscuss': True,
            'employeePortalBackUrl': '/chat/',
            'discuss_public_thread': Store.one(channel_user),
        })
        return request.render('mail.discuss_public_channel_template', {
            'data': store.get_result(),
            'session_info': channel_user.env['ir.http'].session_info(),
            'employee_portal_discuss': True,
            'employee_portal_back_url': '/chat/',
            'employee_portal_home_url': '/my/employee',
        })

    @http.route('/chat/manifest.webmanifest', type='http', auth='public', methods=['GET'])
    def absar_chat_manifest(self):
        manifest = {
            'name': 'Absar Chat',
            'short_name': 'Absar Chat',
            'description': 'Absar internal employee communication',
            'start_url': '/chat/',
            'scope': '/chat/',
            'display': 'standalone',
            'background_color': '#0b1220',
            'theme_color': '#0b1220',
            'icons': [
                {
                    'src': '/absar_chat_pwa/static/icons/icon-192.png',
                    'sizes': '192x192',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
                {
                    'src': '/absar_chat_pwa/static/icons/icon-512.png',
                    'sizes': '512x512',
                    'type': 'image/png',
                    'purpose': 'any maskable',
                },
            ],
        }
        return request.make_response(
            json.dumps(manifest),
            headers=[
                ('Content-Type', 'application/manifest+json; charset=utf-8'),
                ('Cache-Control', 'no-cache'),
            ],
        )

    @http.route('/chat/service-worker.js', type='http', auth='public', methods=['GET'])
    def absar_chat_service_worker(self):
        code = r"""
const CACHE_NAME = 'absar-chat-shell-v6';
const STATIC_ASSETS = [
  '/chat/manifest.webmanifest',
  '/absar_chat_pwa/static/icons/icon-192.png',
  '/absar_chat_pwa/static/icons/icon-512.png',
  '/absar_chat_pwa/static/src/css/absar_chat_home.css',
  '/absar_chat_pwa/static/src/js/absar_chat_home.js'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS).catch(() => {})));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Never cache authenticated navigation, JSON-RPC, websocket or Odoo Discuss data.
  if (event.request.mode === 'navigate' || url.pathname.startsWith('/web/') ||
      url.pathname.startsWith('/mail/') || url.pathname.startsWith('/discuss/') ||
      url.pathname.startsWith('/employee_portal/') || url.pathname.startsWith('/websocket') ||
      url.pathname.startsWith('/longpolling')) {
    return;
  }
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
  }
});
"""
        return request.make_response(code, headers=[
            ('Content-Type', 'application/javascript; charset=utf-8'),
            ('Service-Worker-Allowed', '/chat/'),
            ('Cache-Control', 'no-cache'),
        ])
