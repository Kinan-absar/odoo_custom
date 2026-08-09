import logging
import secrets
from html import escape

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    telegram_chat_id = fields.Char(string='Telegram Chat ID', copy=False, readonly=True)
    telegram_username = fields.Char(string='Telegram Username', copy=False, readonly=True)
    telegram_link_token = fields.Char(string='Telegram Link Token', copy=False, readonly=True)
    telegram_connected = fields.Boolean(string='Telegram Connected', compute='_compute_telegram_connected')

    @api.depends('telegram_chat_id')
    def _compute_telegram_connected(self):
        for user in self:
            user.telegram_connected = bool(user.telegram_chat_id)

    def _ensure_telegram_link_token(self):
        self.ensure_one()
        if not self.telegram_link_token:
            self.sudo().write({'telegram_link_token': secrets.token_urlsafe(24)})
        return self.telegram_link_token

    def action_disconnect_telegram(self):
        self.sudo().write({
            'telegram_chat_id': False,
            'telegram_username': False,
            'telegram_link_token': False,
        })
        return True


class EmployeePortalTelegramConfig(models.Model):
    _name = 'employee.portal.telegram.config'
    _description = 'Employee Portal Telegram Configuration'

    name = fields.Char(default='Telegram Notifications', required=True)
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(string='Enable Telegram Notifications', default=False)
    bot_token = fields.Char(string='Bot Token', groups='base.group_system')
    bot_username = fields.Char(string='Bot Username', help='Without @, for example absar_approvals_bot')
    webhook_secret = fields.Char(string='Webhook Secret', readonly=True, copy=False)
    webhook_url = fields.Char(string='Webhook URL', compute='_compute_webhook_url')

    @api.depends('webhook_secret')
    def _compute_webhook_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            rec.webhook_url = (
                f"{base_url}/employee_portal/telegram/webhook/{rec.webhook_secret}"
                if base_url and rec.webhook_secret else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('webhook_secret', secrets.token_urlsafe(32))
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if not rec.webhook_secret:
                vals.setdefault('webhook_secret', secrets.token_urlsafe(32))
        return super().write(vals)

    def _telegram_api(self, method, payload=None, timeout=15):
        self.ensure_one()
        if not self.bot_token:
            raise UserError(_('Please enter the Telegram Bot Token first.'))
        url = f"https://api.telegram.org/bot{self.bot_token}/{method}"
        try:
            response = requests.post(url, json=payload or {}, timeout=timeout)
            data = response.json()
        except Exception as exc:
            raise UserError(_('Telegram connection failed: %s') % exc) from exc
        if not response.ok or not data.get('ok'):
            raise UserError(_('Telegram API error: %s') % (data.get('description') or response.text))
        return data.get('result')

    def action_test_bot(self):
        self.ensure_one()
        result = self._telegram_api('getMe')
        username = result.get('username')
        values = {}
        if username and username != self.bot_username:
            values['bot_username'] = username
        if values:
            self.write(values)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Telegram'), 'message': _('Connection successful. Bot: @%s') % (username or self.bot_username or ''), 'type': 'success', 'sticky': False},
        }

    def action_configure_webhook(self):
        self.ensure_one()
        if not self.webhook_secret:
            self.write({'webhook_secret': secrets.token_urlsafe(32)})
        if not self.webhook_url:
            raise UserError(_('Odoo Base URL is not configured. Set web.base.url to your public HTTPS Odoo URL.'))
        result = self._telegram_api('setWebhook', {
            'url': self.webhook_url,
            'allowed_updates': ['message'],
            'drop_pending_updates': False,
        })
        if result is not True:
            _logger.info('Telegram setWebhook result: %s', result)
        self.enabled = True
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Telegram'), 'message': _('Webhook configured successfully. Notifications are enabled.'), 'type': 'success', 'sticky': False},
        }

    def action_disable_webhook(self):
        self.ensure_one()
        self._telegram_api('deleteWebhook', {'drop_pending_updates': False})
        self.enabled = False
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Telegram'), 'message': _('Webhook removed and notifications disabled.'), 'type': 'success', 'sticky': False},
        }


class EmployeePortalTelegramService(models.AbstractModel):
    _name = 'employee.portal.telegram.service'
    _description = 'Employee Portal Telegram Notification Service'

    def _get_config(self):
        return self.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
        ], order='id desc', limit=1)

    def _absolute_url(self, path):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        if not path:
            return base_url
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return f"{base_url}/{path.lstrip('/')}"

    def send_to_user(self, user, title, body, path=None):
        if not user or not user.sudo().telegram_chat_id:
            return False
        config = self._get_config()
        if not config or not config.bot_token:
            return False

        text = f"🔔 <b>{escape(str(title or ''))}</b>\n\n{escape(str(body or ''))}"
        payload = {
            'chat_id': user.sudo().telegram_chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
        if path:
            payload['reply_markup'] = {
                'inline_keyboard': [[{
                    'text': 'Open in Odoo',
                    'url': self._absolute_url(path),
                }]]
            }
        try:
            config._telegram_api('sendMessage', payload, timeout=3)
            return True
        except Exception:
            _logger.exception('Failed to send Telegram notification to user %s', user.id)
            return False
