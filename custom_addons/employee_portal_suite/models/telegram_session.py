from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        config = self.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
        ], order='id desc', limit=1)
        info.update({
            'employee_portal_telegram_connected': bool(user.telegram_chat_id),
            'employee_portal_telegram_connect_available': bool(
                not user._is_public() and config and config.bot_username
            ),
        })
        return info
