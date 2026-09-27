{
    "name": "ABSAR Premium Backend",
    "version": "18.0.5.0.0",
    "category": "Themes/Backend",
    "summary": "Configurable Odoo 18 backend appearance and improved Arabic PDF font",
    "description": """
ABSAR Premium Backend
=====================
A lightweight configurable Odoo 18 Enterprise backend module.

Features:
- Optional custom backend primary color and hover color
- Backend font selection
- Arabic QWeb/PDF report font selection
- Toggle rounded backend buttons
- Toggle rounded application icons
- One-click restore to Odoo defaults
- Keeps Odoo's original appearance whenever custom color/font settings are empty
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/report_font_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/rounded_apps.scss",
            "absar_premium_backend/static/src/scss/dynamic_theme.scss",
            "absar_premium_backend/static/src/js/theme_service.js",
        ],
        "web.report_assets_common": [
            "absar_premium_backend/static/src/scss/report_arabic_font.scss",
        ],
    },
    "installable": True,
    "application": False,
}
