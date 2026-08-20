import json
import logging

from werkzeug.utils import redirect

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class EmployeePortalTelegramController(http.Controller):

    @http.route('/my/employee/telegram/connect', type='http', auth='user', website=True)
    def telegram_connect(self, **kwargs):
        config = request.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
        ], order='id desc', limit=1)
        if not config or not config.bot_username:
            return request.redirect('/my/employee?telegram=not_configured')
        token = request.env.user._ensure_telegram_link_token()
        return redirect(f"https://t.me/{config.bot_username.lstrip('@')}?start={token}")

    @http.route('/my/employee/telegram/disconnect', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def telegram_disconnect(self, **kwargs):
        request.env.user.action_disconnect_telegram()
        return request.redirect('/my/employee?telegram=disconnected')

    @http.route('/employee_portal/telegram/webhook/<string:secret>', type='http', auth='public', methods=['POST'], csrf=False, save_session=False)
    def telegram_webhook(self, secret, **kwargs):
        config = request.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
            ('webhook_secret', '=', secret),
        ], limit=1)
        if not config:
            return request.make_response('Not Found', status=404)

        try:
            update = json.loads(request.httprequest.data.decode('utf-8') or '{}')
            message = update.get('message') or {}
            text = (message.get('text') or '').strip()
            chat = message.get('chat') or {}
            if text.startswith('/start') and chat.get('id'):
                parts = text.split(maxsplit=1)
                token = parts[1].strip() if len(parts) > 1 else ''
                if token:
                    user = request.env['res.users'].sudo().search([
                        ('telegram_link_token', '=', token),
                        ('telegram_link_token_expires_at', '>=', request.env.cr.now()),
                        ('active', '=', True),
                    ], limit=1)
                    if user:
                        user.write({
                            'telegram_chat_id': str(chat['id']),
                            'telegram_username': chat.get('username') or False,
                            'telegram_link_token': False,
                            'telegram_link_token_expires_at': False,
                        })
                        config._telegram_api('sendMessage', {
                            'chat_id': chat['id'],
                            'text': f"✅ Telegram connected to your Odoo account: {user.name}",
                        })
                    else:
                        config._telegram_api('sendMessage', {
                            'chat_id': chat['id'],
                            'text': 'This Odoo connection link is invalid or has already been used. Please generate a new link from Odoo.',
                        })
        except Exception:
            _logger.exception('Telegram webhook processing failed')
        return request.make_response('OK')
