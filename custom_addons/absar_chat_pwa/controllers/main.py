# -*- coding: utf-8 -*-
import json
from urllib.parse import urlencode

from odoo import http, _
from odoo.http import request
from odoo.addons.employee_portal_suite.controllers.portal_native_discuss import (
    EmployeePortalNativeDiscussController,
)


class AbsarChatPWAController(EmployeePortalNativeDiscussController):
    """Installable Absar Chat shell backed by the existing Employee Portal Discuss.

    The important rule here is that Absar Chat does *not* create a second Discuss
    bootstrap.  A conversation is opened through the exact, already-proven
    ``/my/employee/discuss/channel/<id>`` route from ``employee_portal_suite``.
    The PWA manifest has root scope, so that native Discuss route remains inside
    the installed Absar Chat window rather than falling back to a browser tab.
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
        """Bridge into the exact working Employee Portal native Discuss route.

        We intentionally redirect instead of re-rendering ``mail.discuss_public_channel_template``
        on a new URL. Odoo 18's Discuss client action restores its active thread from
        the canonical public Discuss route; rendering it on ``/chat/channel/...`` caused
        ``DiscussClientAction.parseActiveId`` to receive an invalid/null active id.
        """
        user = self._employee_user()
        if not user:
            return request.redirect('/my/employee')

        channel = request.env['discuss.channel'].sudo().browse(channel_id).exists()
        if not self._is_allowed_channel(channel, user):
            return request.not_found()

        # Preserve the call auto-answer flags used by the existing RTC patch.
        params = {'absar_chat': '1'}
        for key in ('auto_answer', 'auto_video'):
            value = request.params.get(key)
            if value in ('0', '1'):
                params[key] = value
        target = '/my/employee/discuss/channel/%s?%s' % (channel.id, urlencode(params))
        return request.redirect(target)

    @http.route('/chat/manifest.webmanifest', type='http', auth='public', methods=['GET'])
    def absar_chat_manifest(self):
        manifest = {
            'name': 'Absar Chat',
            'short_name': 'Absar Chat',
            'description': 'Absar internal employee communication',
            'start_url': '/chat/',
            # Manifest scope deliberately includes the canonical Employee Portal Discuss
            # conversation route used by Absar Chat, keeping it inside the installed PWA.
            # The service worker itself stays scoped to /chat/ so it cannot interfere
            # with normal Odoo/portal pages.
            'scope': '/',
            'display': 'standalone',
            'background_color': '#f6f8fb',
            'theme_color': '#ffffff',
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
const CACHE_NAME = 'absar-chat-shell-v7';
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
  // Never cache authenticated navigation, JSON-RPC, websocket or Discuss data.
  if (event.request.mode === 'navigate' || url.pathname.startsWith('/web/') ||
      url.pathname.startsWith('/mail/') || url.pathname.startsWith('/discuss/') ||
      url.pathname.startsWith('/my/employee/') || url.pathname.startsWith('/employee_portal/') ||
      url.pathname.startsWith('/websocket') || url.pathname.startsWith('/longpolling')) {
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
