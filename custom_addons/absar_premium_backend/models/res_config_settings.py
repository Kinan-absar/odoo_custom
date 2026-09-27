import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    absar_primary_color = fields.Char(
        string="Primary Color",
        config_parameter="absar_premium_backend.primary_color",
        help="Optional custom backend primary color in #RRGGBB format. Leave empty to use Odoo's original color.",
    )
    absar_primary_hover_color = fields.Char(
        string="Primary Hover Color",
        config_parameter="absar_premium_backend.primary_hover_color",
        help="Optional hover/pressed color in #RRGGBB format. Leave empty to calculate it automatically from the primary color.",
    )
    absar_backend_font = fields.Selection(
        [
            ("odoo", "Odoo Default"),
            ("system", "System UI"),
            ("arial", "Arial"),
            ("tahoma", "Tahoma"),
            ("trebuchet", "Trebuchet MS"),
            ("georgia", "Georgia"),
        ],
        string="Backend Font",
        default="odoo",
        config_parameter="absar_premium_backend.backend_font",
    )
    absar_report_arabic_font = fields.Selection(
        [
            ("noto", "Noto Sans Arabic"),
            ("dejavu", "DejaVu Sans"),
            ("tahoma", "Tahoma"),
            ("arial", "Arial"),
        ],
        string="Arabic Report Font",
        default="noto",
        config_parameter="absar_premium_backend.report_arabic_font",
        help="Font used for QWeb/PDF reports. Noto Sans Arabic is recommended when available on the server.",
    )
    absar_rounded_buttons = fields.Boolean(
        string="Rounded Buttons",
        default=True,
        config_parameter="absar_premium_backend.rounded_buttons",
    )
    absar_rounded_apps = fields.Boolean(
        string="Rounded App Icons",
        default=True,
        config_parameter="absar_premium_backend.rounded_apps",
    )

    @api.constrains("absar_primary_color", "absar_primary_hover_color")
    def _check_absar_hex_colors(self):
        for record in self:
            for field_name in ("absar_primary_color", "absar_primary_hover_color"):
                value = (record[field_name] or "").strip()
                if value and not HEX_COLOR_RE.match(value):
                    raise ValidationError("Theme colors must use #RRGGBB format, for example #875A7B.")

    def action_absar_reset_theme(self):
        keys = [
            "absar_premium_backend.primary_color",
            "absar_premium_backend.primary_hover_color",
            "absar_premium_backend.backend_font",
            "absar_premium_backend.report_arabic_font",
            "absar_premium_backend.rounded_buttons",
            "absar_premium_backend.rounded_apps",
        ]
        self.env["ir.config_parameter"].sudo().search([("key", "in", keys)]).unlink()
        return {"type": "ir.actions.client", "tag": "reload"}
