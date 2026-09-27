{
    "name": "ABSAR Rounded Apps & Buttons",
    "version": "18.0.4.3.0",
    "category": "Themes/Backend",
    "summary": "Rounded Odoo 18 backend controls with ABSAR blue primary color",
    "description": """
ABSAR Rounded App Icons
=======================
Minimal Odoo 18 Enterprise backend visual module.

This version keeps the rounded application icons and backend buttons and adds
the ABSAR #57A2DE primary backend accent. It does not redesign forms, fields,
lists, kanban, chatter, dialogs, spacing, or business logic.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise"],
    "assets": {
        "web._assets_primary_variables": [
            "absar_premium_backend/static/src/scss/primary_variables.scss",
        ],
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/rounded_apps.scss",
            "absar_premium_backend/static/src/scss/primary_overrides.scss",
        ],
    },
    "installable": True,
    "application": False,
}
