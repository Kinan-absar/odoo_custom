{
    "name": "ABSAR Rounded Apps & Buttons",
    "version": "18.0.4.6.0",
    "category": "Themes/Backend",
    "summary": "Rounded Odoo 18 backend controls and improved Arabic PDF font",
    "description": """
ABSAR Rounded App Icons
=======================
Minimal Odoo 18 Enterprise backend visual module.

This version keeps Odoo's original primary/brand colors, preserves rounded
application icons and backend buttons, and improves Arabic typography in
QWeb/PDF reports using Noto Sans Arabic with DejaVu Sans fallback. It adds restrained premium polish to forms, dialogs, dropdowns, lists, kanban
cards, and field focus states while keeping Odoo's native colors, typography,
layout model, and business logic unchanged.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/rounded_apps.scss",
            "absar_premium_backend/static/src/scss/premium_details.scss",
        ],
        "web.report_assets_common": [
            "absar_premium_backend/static/src/scss/report_arabic_font.scss",
        ],
    },
    "installable": True,
    "application": False,
}
