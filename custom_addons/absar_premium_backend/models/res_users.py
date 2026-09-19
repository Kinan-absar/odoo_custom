from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    absar_premium_theme_enabled = fields.Boolean(
        string="ABSAR Premium Theme",
        default=True,
        help="Enable the ABSAR premium backend interface for this user.",
    )

    @api.model
    def absar_get_theme_enabled(self):
        return bool(self.env.user.sudo().absar_premium_theme_enabled)

    @api.model
    def absar_set_theme_enabled(self, enabled):
        self.env.user.sudo().write({"absar_premium_theme_enabled": bool(enabled)})
        return True
