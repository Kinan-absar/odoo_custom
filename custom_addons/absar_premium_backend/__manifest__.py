{
    "name": "ABSAR Premium Backend",
    "version": "18.0.5.2.0",
    "category": "Themes/Backend",
    "summary": "Configurable Odoo 18 backend colors/fonts with reliable report typography",
    "description": """
ABSAR Premium Backend
=====================
Built from the stable final theme and corrected configurable build.

Features:
- Optional backend primary + hover/pressed colors
- Independent link + link hover/pressed colors
- Clickable HTML color pickers plus HEX fields
- Expanded backend UI font list
- Working on/off controls for rounded buttons and application icons
- PDF/report font selector based on Odoo's native company.font mechanism
- Adds Noto Sans Arabic to Odoo's native report font choices
- Forces report header/body/footer descendants to inherit the selected report font,
  fixing mixed Arabic address lines such as "42317 المدينة المنورة"
- Restore Odoo defaults button

When custom colors are empty and Backend UI Font is Odoo Default, the backend
keeps Odoo's native colors and typography.
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
