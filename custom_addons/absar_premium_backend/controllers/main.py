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

REPORT_FONT_MAP = {
    "noto": "'Noto Sans Arabic', 'Noto Sans Arabic UI', 'DejaVu Sans', Arial, sans-serif",
    "dejavu": "'DejaVu Sans', Arial, sans-serif",
    "tahoma": "Tahoma, 'DejaVu Sans', Arial, sans-serif",
    "arial": "Arial, 'DejaVu Sans', sans-serif",
}


def _as_bool(value, default=True):
    if value in (None, False, "", "False", "false", "0"):
        return default if value in (None, False, "") else False
    return True


class AbsarThemeController(http.Controller):

    @http.route("/absar_premium_backend/theme_config", type="json", auth="user")
    def theme_config(self):
        params = request.env["ir.config_parameter"].sudo()
        backend_font = params.get_param("absar_premium_backend.backend_font", "odoo")
        report_font = params.get_param("absar_premium_backend.report_arabic_font", "noto")
        return {
            "primary_color": params.get_param("absar_premium_backend.primary_color", "") or "",
            "primary_hover_color": params.get_param("absar_premium_backend.primary_hover_color", "") or "",
            "backend_font": backend_font,
            "backend_font_css": FONT_MAP.get(backend_font, ""),
            "report_font": report_font,
            "report_font_css": REPORT_FONT_MAP.get(report_font, REPORT_FONT_MAP["noto"]),
            "rounded_buttons": _as_bool(params.get_param("absar_premium_backend.rounded_buttons"), True),
            "rounded_apps": _as_bool(params.get_param("absar_premium_backend.rounded_apps"), True),
        }
