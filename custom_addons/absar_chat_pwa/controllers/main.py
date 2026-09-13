# -*- coding: utf-8 -*-
import base64
import json

from odoo import http, _
from odoo.http import request
from odoo.addons.employee_portal_suite.controllers.portal_native_discuss import (
    EmployeePortalNativeDiscussController,
)


class AbsarChatPWAController(EmployeePortalNativeDiscussController):
    """Standalone Absar Chat PWA.

    The UI is purpose-built, but data/actions remain in the existing Employee
    Portal communication stack (portal.chat.thread, discuss.channel,
    mail.message, call endpoints). No second chat database is introduced.
    """

    @http.route(['/chat', '/chat/'], type='http', auth='user', website=True, methods=['GET'])
    def absar_chat_home(self, **kwargs):
        user = self._employee_user()
        if not user:
            return request.render('absar_chat_pwa.access_denied_page', {
                'title': _('Access Restricted'),
                'message': _('Absar Chat is restricted to authorized company employees only.'),
            })
        employee = request.env['hr.employee'].sudo().search([
            ('active', '=', True), ('user_id', '=', user.id),
        ], limit=1)
        return request.render('absar_chat_pwa.chat_home', {
            'current_user': user,
            'current_employee': employee,
            'current_avatar': '/employee_portal/call/avatar/%s' % user.id,
        })

    @http.route('/chat/attachment/<int:attachment_id>', type='http', auth='user', csrf=False)
    def absar_chat_attachment_preview(self, attachment_id, **kwargs):
        """Inline preview route with channel membership verification."""
        user = self._employee_user()
        if not user:
            return request.not_found()
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or attachment.res_model != 'discuss.channel':
            return request.not_found()
        channel = request.env['discuss.channel'].sudo().browse(attachment.res_id).exists()
        if not channel or user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
            return request.not_found()
        raw = base64.b64decode(attachment.datas or b'')
        filename = (attachment.name or 'attachment').replace('"', '')
        return request.make_response(raw, headers=[
            ('Content-Type', attachment.mimetype or 'application/octet-stream'),
            ('Content-Length', str(len(raw))),
            ('Content-Disposition', 'inline; filename="%s"' % filename),
            ('Cache-Control', 'private, max-age=300'),
        ])

    @http.route('/chat/manifest.webmanifest', type='http', auth='public', methods=['GET'])
    def absar_chat_manifest(self):
        manifest = {
            'name': 'Absar Chat',
            'short_name': 'Absar Chat',
            'description': 'ABSAR internal employee messaging and calls',
            'start_url': '/chat/',
            'scope': '/chat/',
            'display': 'standalone',
            'background_color': '#f5f7f9',
            'theme_color': '#ffffff',
            'orientation': 'any',
            'icons': [
                {'src': '/absar_chat_pwa/static/icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any maskable'},
                {'src': '/absar_chat_pwa/static/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'},
            ],
        }
        return request.make_response(json.dumps(manifest), headers=[
            ('Content-Type', 'application/manifest+json; charset=utf-8'),
            ('Cache-Control', 'no-cache'),
        ])

    @http.route('/chat/service-worker.js', type='http', auth='public', methods=['GET'])
    def absar_chat_service_worker(self):
        # Never cache authenticated HTML, RPC, messages, attachments or call data.
        code = r"""
const CACHE_NAME = 'absar-chat-static-v14';
const STATIC_ASSETS = [
  '/chat/manifest.webmanifest',
  '/absar_chat_pwa/static/icons/icon-192.png',
  '/absar_chat_pwa/static/icons/icon-512.png',
  '/absar_chat_pwa/static/src/css/absar_chat.css',
  '/absar_chat_pwa/static/src/css/call_widget.css',
  '/absar_chat_pwa/static/src/js/portal_call_bridge.js',
  '/absar_chat_pwa/static/src/js/absar_chat.js'
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
  if (event.request.mode === 'navigate' || event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/employee_portal/') || url.pathname.startsWith('/web/') ||
      url.pathname.startsWith('/mail/') || url.pathname.startsWith('/chat/attachment/') ||
      url.pathname.startsWith('/websocket') || url.pathname.startsWith('/longpolling')) return;
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
