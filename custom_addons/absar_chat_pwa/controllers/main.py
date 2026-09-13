# -*- coding: utf-8 -*-
import base64
import json

from odoo import http, _
from odoo.http import request
from odoo.addons.employee_portal_suite.controllers.portal_native_discuss import (
    EmployeePortalNativeDiscussController,
)
from odoo.addons.employee_portal_suite.controllers.portal_chat import PortalChatController


class AbsarChatPWAController(EmployeePortalNativeDiscussController):
    """Standalone Absar Chat PWA shell and protected attachment preview."""

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

    def _authorized_attachment_channel(self, attachment, user):
        """Return the Discuss channel for an attachment if the user may see it."""
        channel = request.env['discuss.channel']
        if attachment.res_model == 'discuss.channel':
            channel = request.env['discuss.channel'].sudo().browse(attachment.res_id).exists()
        elif attachment.res_model == 'mail.message':
            message = request.env['mail.message'].sudo().browse(attachment.res_id).exists()
            if message and message.model == 'discuss.channel':
                channel = request.env['discuss.channel'].sudo().browse(message.res_id).exists()
        else:
            # Attachments linked to a Discuss message through the M2M can still
            # retain discuss.channel as their resource in some Odoo flows. If a
            # future Odoo change stores them differently, resolve the owning
            # message explicitly rather than exposing arbitrary attachments.
            message = request.env['mail.message'].sudo().search([
                ('attachment_ids', 'in', attachment.id),
                ('model', '=', 'discuss.channel'),
            ], limit=1)
            if message:
                channel = request.env['discuss.channel'].sudo().browse(message.res_id).exists()
        if not channel or user.partner_id.id not in channel.channel_member_ids.partner_id.ids:
            return request.env['discuss.channel']
        return channel

    @http.route('/chat/attachment/<int:attachment_id>', type='http', auth='user', csrf=False)
    def absar_chat_attachment_preview(self, attachment_id, **kwargs):
        user = self._employee_user()
        if not user:
            return request.not_found()
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        if not attachment or not self._authorized_attachment_channel(attachment, user):
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
        code = r"""
const CACHE_NAME = 'absar-chat-static-v15';
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
      url.pathname.startsWith('/chat/api/') || url.pathname.startsWith('/websocket') ||
      url.pathname.startsWith('/longpolling')) return;
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


class AbsarChatAPIController(PortalChatController):
    """PWA-specific wrappers around the proven Employee Portal chat backend.

    These routes deliberately reuse PortalChatController's authorization and
    message logic. The only extra step is to enforce the attachment relation on
    the posted mail.message and return the freshly serialized message, making
    attachment-only messages deterministic for the standalone PWA.
    """

    @http.route('/chat/api/upload', type='json', auth='user', csrf=False)
    def absar_chat_upload(self, thread_id=None, filename=None, mimetype=None, data=None):
        return super().chat_upload(
            thread_id=thread_id,
            filename=filename,
            mimetype=mimetype,
            data=data,
        )

    @http.route('/chat/api/send', type='json', auth='user', csrf=False)
    def absar_chat_send(self, thread_id=None, body=None, reply_to_id=None, attachment_ids=None):
        result = super().chat_send(
            thread_id=thread_id,
            body=body,
            reply_to_id=reply_to_id,
            attachment_ids=attachment_ids,
        )
        if not result or result.get('error') or not result.get('message_id'):
            return result

        thread = self._thread(thread_id)
        if not thread:
            return result
        user = self._user()
        channel = self._channel(thread)
        message = request.env['mail.message'].sudo().browse(result['message_id']).exists()
        if not message:
            return result

        valid_ids = [int(x) for x in (attachment_ids or []) if str(x).isdigit()]
        if valid_ids:
            candidate_attachments = request.env['ir.attachment'].sudo().browse(valid_ids).exists()
            already_linked_ids = set(message.sudo().attachment_ids.ids)
            attachments = candidate_attachments.filtered(
                lambda a: (a.res_model == 'discuss.channel' and a.res_id == channel.id)
                or a.id in already_linked_ids
            )
            if attachments:
                # message_post normally links these already. Re-adding the M2M
                # relation is idempotent and protects attachment-only posts from
                # version-specific Discuss attachment handling differences.
                message.sudo().write({'attachment_ids': [(4, att.id) for att in attachments]})

        result['message'] = self._message_row(message, channel, user)
        return result
