{
    "name": "ABSAR Premium Backend",
    "version": "18.0.5.1.1",
    "category": "Themes/Backend",
    "summary": "Configurable Odoo 18 backend color/font with improved Arabic PDF typography",
    "description": """
ABSAR Premium Backend
=====================
Built from the stable 18.0.4.5.0 final version.

Features:
- Optional backend primary color and hover color from Settings
- Optional backend font from Settings
- Toggle rounded buttons and application icons
- Restore Odoo defaults button
- Static Noto Sans Arabic report typography for reliable PDF rendering
- Extra contact/address selectors for mixed Arabic/English address lines

When Primary Color is empty and Backend Font is Odoo Default, Odoo keeps its
native colors and typography.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "data": [
        "views/res_config_settings_views.xml",
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
