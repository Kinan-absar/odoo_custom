{
    "name": "ABSAR Premium Backend",
    "version": "18.0.3.0.0",
    "category": "Themes/Backend",
    "summary": "Premium high-contrast backend design system for Odoo 18 Enterprise",
    "description": """
ABSAR Premium Backend 3.0
=========================
A complete, coherent visual system for Odoo 18 Enterprise with a per-user
ON/OFF switch in the user menu. The redesign covers navbar, app launcher,
search/control panel, forms, fields, status bars, notebooks, lists, kanban,
chatter, dialogs, badges, settings and responsive behavior.

No accounting or business workflow logic is changed.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise", "mail"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/premium.scss",
            "absar_premium_backend/static/src/js/theme_toggle.js",
        ],
    },
    "installable": True,
    "application": False,
}
