{
    "name": "ABSAR Premium Backend",
    "version": "18.0.1.0.0",
    "category": "Themes/Backend",
    "summary": "Premium visual redesign for the Odoo 18 backend",
    "description": """
ABSAR Premium Backend
=====================
A presentation-layer redesign for Odoo 18 Enterprise focused on forms,
fields, headers, status bars, buttons, notebooks, lists, kanban cards,
chatter, dialogs, navigation, badges and responsive behavior.

The module intentionally avoids changing accounting or business logic.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "mail"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/_tokens.scss",
            "absar_premium_backend/static/src/scss/_base.scss",
            "absar_premium_backend/static/src/scss/_navbar.scss",
            "absar_premium_backend/static/src/scss/_control_panel.scss",
            "absar_premium_backend/static/src/scss/_forms.scss",
            "absar_premium_backend/static/src/scss/_fields.scss",
            "absar_premium_backend/static/src/scss/_buttons.scss",
            "absar_premium_backend/static/src/scss/_statusbar.scss",
            "absar_premium_backend/static/src/scss/_notebook.scss",
            "absar_premium_backend/static/src/scss/_list.scss",
            "absar_premium_backend/static/src/scss/_kanban.scss",
            "absar_premium_backend/static/src/scss/_chatter.scss",
            "absar_premium_backend/static/src/scss/_dialogs.scss",
            "absar_premium_backend/static/src/scss/_badges.scss",
            "absar_premium_backend/static/src/scss/_responsive.scss",
            "absar_premium_backend/static/src/scss/backend.scss",
        ],
    },
    "installable": True,
    "application": False,
}
