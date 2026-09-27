import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    absar_primary_color = fields.Char(
        string="Primary Color",
        config_parameter="absar_premium_backend.primary_color",
        help="Optional custom backend primary color in #RRGGBB format. Leave empty to keep Odoo's native color.",
    )
    absar_primary_hover_color = fields.Char(
        string="Primary Hover / Pressed Color",
        config_parameter="absar_premium_backend.primary_hover_color",
        help="Hover/pressed color for primary controls. Leave empty to derive a darker shade automatically.",
    )
    absar_link_color = fields.Char(
        string="Link Color",
        config_parameter="absar_premium_backend.link_color",
        help="Optional color for clickable links. Leave empty to follow Odoo/the selected primary color.",
    )
    absar_link_hover_color = fields.Char(
        string="Link Hover / Pressed Color",
        config_parameter="absar_premium_backend.link_hover_color",
        help="Optional color used when a link is hovered, focused, or pressed. Leave empty to derive it automatically.",
    )
    absar_backend_font = fields.Selection(
        [
            ("odoo", "Odoo Default"),
            ("system", "System UI"),
            ("segoe", "Segoe UI"),
            ("lato", "Lato"),
            ("roboto", "Roboto"),
            ("opensans", "Open Sans"),
            ("montserrat", "Montserrat"),
            ("raleway", "Raleway"),
            ("oswald", "Oswald"),
            ("tajawal", "Tajawal"),
            ("firamono", "Fira Mono"),
            ("noto", "Noto Sans"),
            ("ubuntu", "Ubuntu"),
            ("helvetica", "Helvetica / Helvetica Neue"),
            ("arial", "Arial"),
            ("tahoma", "Tahoma"),
            ("verdana", "Verdana"),
            ("trebuchet", "Trebuchet MS"),
            ("georgia", "Georgia"),
            ("times", "Times New Roman"),
            ("courier", "Courier New"),
        ],
        string="Backend UI Font",
        default="odoo",
        config_parameter="absar_premium_backend.backend_font",
    )
    absar_report_font = fields.Selection(
        related="company_id.font",
        readonly=False,
        string="PDF / Report Font",
    )

    # Do NOT use config_parameter directly for these booleans.  Odoo may remove
    # a config parameter when a Boolean is False, which made an unchecked option
    # look enabled again because the controller treated a missing value as True.
    # We explicitly persist 1/0 in get_values/set_values instead.
    absar_rounded_buttons = fields.Boolean(string="Rounded Buttons", default=True)
    absar_rounded_apps = fields.Boolean(string="Rounded App Icons", default=True)

    @api.model
    def get_values(self):
        values = super().get_values()
        params = self.env["ir.config_parameter"].sudo()
        values.update(
            absar_rounded_buttons=params.get_param(
                "absar_premium_backend.rounded_buttons", "1"
            ) in ("1", "true", "True", True),
            absar_rounded_apps=params.get_param(
                "absar_premium_backend.rounded_apps", "1"
            ) in ("1", "true", "True", True),
        )
        return values

    def set_values(self):
        super().set_values()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param(
            "absar_premium_backend.rounded_buttons",
            "1" if self.absar_rounded_buttons else "0",
        )
        params.set_param(
            "absar_premium_backend.rounded_apps",
            "1" if self.absar_rounded_apps else "0",
        )

    @api.constrains(
        "absar_primary_color",
        "absar_primary_hover_color",
        "absar_link_color",
        "absar_link_hover_color",
    )
    def _check_absar_hex_colors(self):
        for record in self:
            for field_name in (
                "absar_primary_color",
                "absar_primary_hover_color",
                "absar_link_color",
                "absar_link_hover_color",
            ):
                value = (record[field_name] or "").strip()
                if value and not HEX_COLOR_RE.match(value):
                    raise ValidationError(
                        "Theme colors must use #RRGGBB format, for example #875A7B."
                    )

    def action_absar_reset_theme(self):
        keys = [
            "absar_premium_backend.primary_color",
            "absar_premium_backend.primary_hover_color",
            "absar_premium_backend.link_color",
            "absar_premium_backend.link_hover_color",
            "absar_premium_backend.backend_font",
        ]
        self.env["ir.config_parameter"].sudo().search([("key", "in", keys)]).unlink()
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("absar_premium_backend.rounded_buttons", "1")
        params.set_param("absar_premium_backend.rounded_apps", "1")
        if self.company_id:
            self.company_id.font = "Lato"
        return {"type": "ir.actions.client", "tag": "reload"}
