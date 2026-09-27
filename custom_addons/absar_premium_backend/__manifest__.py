{
    "name": "ABSAR Rounded Apps & Buttons",
    "version": "18.0.4.5.0",
    "category": "Themes/Backend",
    "summary": "Rounded Odoo 18 backend controls and improved Arabic PDF font",
    "description": """
ABSAR Rounded App Icons
=======================
Minimal Odoo 18 Enterprise backend visual module.

This version keeps Odoo's original primary/brand colors, preserves rounded
application icons and backend buttons, and improves Arabic typography in
QWeb/PDF reports using Noto Sans Arabic with DejaVu Sans fallback. It does not
redesign forms, fields, lists, kanban, chatter, dialogs, spacing, or business
logic.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/rounded_apps.scss",
        ],
        "web.report_assets_common": [
            "absar_premium_backend/static/src/scss/report_arabic_font.scss",
        ],
    },
    "installable": True,
    "application": False,
}
