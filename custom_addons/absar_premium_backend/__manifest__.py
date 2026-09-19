{
    "name": "ABSAR Rounded Apps & Buttons",
    "version": "18.0.4.1.0",
    "category": "Themes/Backend",
    "summary": "Rounds Odoo 18 Enterprise app icons and backend buttons only",
    "description": """
ABSAR Rounded App Icons
=======================
Minimal Odoo 18 Enterprise backend visual module.

This version changes ONLY the shape of application icons and backend buttons.
It does not modify forms, fields, colors, navbar, lists, kanban, chatter, dialogs,
spacing, or business logic.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/rounded_apps.scss",
        ],
    },
    "installable": True,
    "application": False,
}
