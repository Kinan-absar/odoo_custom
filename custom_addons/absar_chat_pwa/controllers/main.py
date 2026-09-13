# -*- coding: utf-8 -*-
import json
import logging
from werkzeug.exceptions import Forbidden, NotFound

from odoo import http, fields, _
from odoo.http import request
from odoo.tools import plaintext2html

_logger = logging.getLogger(__name__)

class AbsarChatController(http.Controller):

    def _get_active_employee(self):
        """
        Verify that the current logged-in user is linked to an active hr.employee.
        Prevents vendor and customer portal users from accessing internal communications.

        NOTE ON SUDO USAGE:
        In standard Odoo, external portal users (base.group_portal) lack read access to
        hr.employee (which is restricted to HR officers/internal users).
        Querying hr.employee without sudo would raise an AccessError for valid portal employees.
        Therefore, sudo() is strictly used HERE AND ONLY HERE as an identity gatekeeper:
        "Does request.env.user correspond to an active company employee?"

        CRITICAL: The resulting employee record is NEVER used to bypass channel or message
        authorization. All conversation access is separately and strictly checked against
        the user's real partner identity (request.env.user.partner_id).
        """
        user = request.env.user
        if not user or user._is_public():
            return False
        employee = request.env['hr.employee'].sudo().search([
            ('user_id', '=', user.id),
            ('active', '=', True)
        ], limit=1)
        return employee

    # -------------------------------------------------------------------------
    # PWA Web Shell & Manifest Routes
    # -------------------------------------------------------------------------

    @http.route(['/chat', '/chat/'], type='http', auth='user', website=False)
    def absar_chat_index(self, **kwargs):
        """
        Primary entry point for Absar Chat PWA.
        Renders a full-screen, standalone application shell without website/portal chrome.
        """
        employee = self._get_active_employee()
        if not employee:
            return request.render('absar_chat_pwa.access_denied_page', {
                'title': _('Access Restricted'),
                'message': _('Absar Chat is restricted to authorized company employees only.'),
            })

        user = request.env.user
        session_info = {
            'uid': user.id,
            'partner_id': user.partner_id.id,
            'partner_name': user.partner_id.name,
            'employee_id': employee.id,
            'employee_name': employee.name,
            'job_title': employee.job_title or '',
            'department': employee.department_id.name if employee.department_id else '',
            'avatar_url': f"/web/image/hr.employee/{employee.id}/avatar_128",
            'company_name': user.company_id.name,
        }

        return request.render('absar_chat_pwa.chat_page', {
            'session_info': session_info,
            'session_info_json': json.dumps(session_info),
        })

    @http.route('/chat/manifest.webmanifest', type='http', auth='public', methods=['GET'])
    def absar_chat_manifest(self):
        manifest_data = {
            "name": "Absar Chat",
            "short_name": "Absar Chat",
            "description": "Internal Company Communication - Powered by Odoo Discuss",
            "start_url": "/chat",
            "scope": "/chat",
            "display": "standalone",
            "orientation": "portrait-primary",
            "background_color": "#090d16",
            "theme_color": "#090d16",
            "icons": [
                {
                    "src": "/absar_chat_pwa/static/icons/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any maskable"
                },
                {
                    "src": "/absar_chat_pwa/static/icons/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable"
                }
            ]
        }
        return request.make_response(
            json.dumps(manifest_data, indent=2),
            headers=[
                ('Content-Type', 'application/manifest+json; charset=utf-8'),
                ('Cache-Control', 'public, max-age=3600'),
            ]
        )

    @http.route('/chat/service-worker.js', type='http', auth='public', methods=['GET'])
    def absar_chat_service_worker(self):
        sw_code = """
const CACHE_NAME = 'absar-chat-static-v2';
const STATIC_ASSETS = [
  '/chat/manifest.webmanifest',
  '/absar_chat_pwa/static/icons/icon-192.png',
  '/absar_chat_pwa/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Absar Chat SW cache failed:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // CRITICAL: Never cache authenticated /chat HTML or dynamic data/API routes!
  // Prevents leaking session/employee information across accounts or logouts.
  if (
    url.pathname.startsWith('/chat/api') ||
    url.pathname.startsWith('/web/dataset') ||
    url.pathname.startsWith('/longpolling') ||
    url.pathname.startsWith('/websocket') ||
    event.request.mode === 'navigate' ||
    url.pathname === '/chat' ||
    url.pathname === '/chat/'
  ) {
    return;
  }

  // Cache-first for genuinely static assets only (icons, manifest)
  if (
    url.pathname.startsWith('/absar_chat_pwa/static/') ||
    url.pathname === '/chat/manifest.webmanifest'
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
  }
});
"""
        return request.make_response(
            sw_code,
            headers=[
                ('Content-Type', 'application/javascript; charset=utf-8'),
                ('Service-Worker-Allowed', '/chat'),
                ('Cache-Control', 'no-cache'),
            ]
        )

    # -------------------------------------------------------------------------
    # JSON-RPC Data Endpoints (Strict Security Validations)
    # -------------------------------------------------------------------------

    @http.route('/chat/api/session', type='json', auth='user')
    def get_session_info(self):
        employee = self._get_active_employee()
        if not employee:
            raise Forbidden(_("Active employee credentials required."))

        user = request.env.user
        return {
            'uid': user.id,
            'partner_id': user.partner_id.id,
            'partner_name': user.partner_id.name,
            'employee_id': employee.id,
            'employee_name': employee.name,
            'job_title': employee.job_title or '',
            'department': employee.department_id.name if employee.department_id else '',
            'avatar_url': f"/web/image/hr.employee/{employee.id}/avatar_128",
            'company_name': user.company_id.name,
        }

    @http.route('/chat/api/channels', type='json', auth='user')
    def get_channels(self):
        """
        Returns authorized channels for the current employee.
        Only returns channels where current partner is an active member.
        Strictly preserves channel filtering parity with employee_portal_suite.
        """
        employee = self._get_active_employee()
        if not employee:
            raise Forbidden(_("Access Denied."))

        partner = request.env.user.partner_id
        domain = [
            ('channel_member_ids.partner_id', '=', partner.id),
            ('active', '=', True),
        ]

        # Respect existing employee_portal_suite channel isolation:
        # Do not expose internal Discuss channels that the employee portal intentionally hides
        if 'is_employee_portal_channel' in request.env['discuss.channel']._fields:
            domain.append(('is_employee_portal_channel', '=', True))

        channels = request.env['discuss.channel'].search(domain, order='write_date desc')
        return [c._get_absar_chat_info(partner) for c in channels]

    @http.route('/chat/api/messages', type='json', auth='user')
    def get_messages(self, channel_id, limit=50, before_id=None):
        """
        Fetch paginated messages for a given channel with strict membership verification.
        """
        employee = self._get_active_employee()
        if not employee:
            raise Forbidden(_("Access Denied."))

        partner = request.env.user.partner_id
        channel = request.env['discuss.channel'].browse(int(channel_id)).exists()

        if not channel:
            raise NotFound(_("Conversation not found."))

        # CRITICAL SECURITY CHECK: Verify user is a member of this channel
        if partner.id not in channel.channel_member_ids.mapped('partner_id.id'):
            raise Forbidden(_("You are not authorized to view messages in this conversation."))

        messages = channel._get_absar_messages_data(partner, limit=limit, before_id=before_id)
        return {
            'channel_id': channel.id,
            'channel_name': channel._get_absar_chat_info(partner)['name'],
            'messages': messages,
        }

    @http.route('/chat/api/message/send', type='json', auth='user')
    def send_message(self, channel_id, body):
        """
        Posts a real Odoo Discuss message using safe HTML sanitization.
        Instantly visible in standard Odoo Discuss and Employee Portal.
        """
        employee = self._get_active_employee()
        if not employee:
            raise Forbidden(_("Access Denied."))

        partner = request.env.user.partner_id
        channel = request.env['discuss.channel'].browse(int(channel_id)).exists()

        if not channel:
            raise NotFound(_("Conversation not found."))

        # CRITICAL SECURITY CHECK: Member verification
        if partner.id not in channel.channel_member_ids.mapped('partner_id.id'):
            raise Forbidden(_("You are not a member of this conversation."))

        raw_body = (body or '').strip()
        if not raw_body:
            return {'error': _("Message cannot be empty.")}

        # NATIVE SANITIZATION: Convert plain composer text into safe HTML
        # Escapes HTML/script tags to prevent injection while preserving line breaks and links
        safe_body = plaintext2html(raw_body)

        # Native Odoo Discuss post: Triggers native mail.message record creation
        # and dispatches notifications across bus.bus to standard Odoo Discuss
        msg = channel.message_post(
            body=safe_body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment'
        )

        # Mark as seen by current user using native Odoo 18 Discuss mechanism
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id.id == partner.id)
        if member:
            if hasattr(member, '_set_last_seen_message_id'):
                member._set_last_seen_message_id(msg.id)
            else:
                member.write({'seen_message_id': msg.id})

        return {
            'success': True,
            'message': {
                'id': msg.id,
                'author_id': msg.author_id.id,
                'author_name': msg.author_id.name,
                'author_avatar': f"/web/image/res.partner/{msg.author_id.id}/avatar_128",
                'body': msg.body,
                'date': fields.Datetime.to_string(msg.date),
                'is_current_user': True,
                'attachment_ids': [],
            }
        }

    @http.route('/chat/api/mark_as_read', type='json', auth='user')
    def mark_as_read(self, channel_id):
        """
        Synchronizes the native Odoo Discuss read marker.
        Clears the unread count in both Absar Chat and standard Odoo Discuss via native API.
        """
        employee = self._get_active_employee()
        if not employee:
            raise Forbidden(_("Access Denied."))

        partner = request.env.user.partner_id
        channel = request.env['discuss.channel'].browse(int(channel_id)).exists()

        if not channel or partner.id not in channel.channel_member_ids.mapped('partner_id.id'):
            return {'success': False}

        member = channel.channel_member_ids.filtered(lambda m: m.partner_id.id == partner.id)
        if member:
            latest_msg = channel.message_ids[:1]
            if latest_msg:
                if hasattr(member, '_set_last_seen_message_id'):
                    member._set_last_seen_message_id(latest_msg.id)
                else:
                    member.write({'seen_message_id': latest_msg.id})

        return {'success': True}

