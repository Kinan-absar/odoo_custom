import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class EmployeePortalNotificationService(models.AbstractModel):
    """Unified employee notification service.

    Web Push is the primary transport for portal/internal employee notifications.
    Telegram is optional legacy fallback only, controlled by system parameter:
    employee_portal.notifications.telegram_fallback = True/False (default False).
    """

    _name = 'employee.portal.notification.service'
    _description = 'Employee Portal Unified Notification Service'

    @api.model
    def _telegram_fallback_enabled(self):
        config = self.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
        ], order='id desc', limit=1)
        if config and 'telegram_fallback_enabled' in config._fields:
            return bool(config.telegram_fallback_enabled)
        value = self.env['ir.config_parameter'].sudo().get_param(
            'employee_portal.notifications.telegram_fallback', 'False'
        )
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on')

    @api.model
    def send_to_user(
        self,
        user,
        title,
        body,
        path=None,
        kind='portal',
        tag=None,
        urgency='normal',
        telegram_fallback=None,
    ):
        if not user or not user.active:
            return False

        delivered = False
        try:
            delivered = self.env['employee.portal.webpush.service'].sudo().send_to_user(
                user,
                title,
                body,
                path=path,
                kind=kind,
                tag=tag,
                urgency=urgency,
            )
        except Exception:
            _logger.exception('Web Push notification failed for user %s', user.id)

        if delivered:
            return True

        if telegram_fallback is None:
            telegram_fallback = self._telegram_fallback_enabled()
        if not telegram_fallback:
            return False

        try:
            return self.env['employee.portal.telegram.service'].sudo().send_to_user(
                user, title, body, path=path
            )
        except Exception:
            _logger.exception('Telegram fallback notification failed for user %s', user.id)
            return False

    @api.model
    def users_with_delivery(self):
        """Return active users who have at least one active push subscription.

        Optional Telegram fallback users are included only when the legacy fallback
        system parameter is enabled.
        """
        push_users = self.env['employee.portal.push.subscription'].sudo().search([
            ('active', '=', True),
            ('user_id.active', '=', True),
        ]).mapped('user_id')

        if self._telegram_fallback_enabled():
            telegram_users = self.env['res.users'].sudo().search([
                ('active', '=', True),
                ('telegram_chat_id', '!=', False),
            ])
            return push_users | telegram_users
        return push_users
