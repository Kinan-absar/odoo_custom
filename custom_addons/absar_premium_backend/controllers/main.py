from odoo import http
from odoo.http import request


FONT_MAP = {
    "odoo": "",
    "system": "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    "arial": "Arial, sans-serif",
    "tahoma": "Tahoma, Arial, sans-serif",
    "trebuchet": "'Trebuchet MS', Arial, sans-serif",
    "georgia": "Georgia, 'Times New Roman', serif",
}


def _as_bool(value, default=True):
    if value in (None, False, ""):
        return default
    return str(value).lower() not in ("false", "0", "no")


class AbsarThemeController(http.Controller):

    @http.route("/absar_premium_backend/theme_config", type="json", auth="user")
    def theme_config(self):
        params = request.env["ir.config_parameter"].sudo()
        backend_font = params.get_param("absar_premium_backend.backend_font", "odoo")
        return {
            "primary_color": params.get_param("absar_premium_backend.primary_color", "") or "",
            "primary_hover_color": params.get_param("absar_premium_backend.primary_hover_color", "") or "",
            "backend_font_css": FONT_MAP.get(backend_font, ""),
            "rounded_buttons": _as_bool(params.get_param("absar_premium_backend.rounded_buttons"), True),
            "rounded_apps": _as_bool(params.get_param("absar_premium_backend.rounded_apps"), True),
        }
