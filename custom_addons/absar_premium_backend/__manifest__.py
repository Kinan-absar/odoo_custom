{
    "name": "ABSAR Premium Backend",
    "version": "18.0.2.0.0",
    "category": "Themes/Backend",
    "summary": "Complete premium visual system for Odoo 18 Enterprise",
    "description": """
ABSAR Premium Backend 2.0
=========================
A coherent presentation-layer redesign for the complete Odoo 18 Enterprise
backend: app launcher, navbar, control panel, forms, fields, status bars,
notebooks, lists, kanban, chatter, dialogs, search panels, settings,
calendar/pivot/graph surfaces and responsive behavior.

No accounting or business workflow logic is changed.
""",
    "author": "ABSAR Alomran",
    "website": "https://www.absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["web", "web_enterprise", "mail"],
    "assets": {
        "web.assets_backend": [
            "absar_premium_backend/static/src/scss/_tokens.scss",
            "absar_premium_backend/static/src/scss/_base.scss",
            "absar_premium_backend/static/src/scss/_home_menu.scss",
            "absar_premium_backend/static/src/scss/_navbar.scss",
            "absar_premium_backend/static/src/scss/_control_panel.scss",
            "absar_premium_backend/static/src/scss/_buttons.scss",
            "absar_premium_backend/static/src/scss/_forms.scss",
            "absar_premium_backend/static/src/scss/_fields.scss",
            "absar_premium_backend/static/src/scss/_statusbar.scss",
            "absar_premium_backend/static/src/scss/_notebook.scss",
            "absar_premium_backend/static/src/scss/_list.scss",
            "absar_premium_backend/static/src/scss/_kanban.scss",
            "absar_premium_backend/static/src/scss/_search_panel.scss",
            "absar_premium_backend/static/src/scss/_chatter.scss",
            "absar_premium_backend/static/src/scss/_dialogs.scss",
            "absar_premium_backend/static/src/scss/_views.scss",
            "absar_premium_backend/static/src/scss/_settings.scss",
            "absar_premium_backend/static/src/scss/_badges.scss",
            "absar_premium_backend/static/src/scss/_responsive.scss",
            "absar_premium_backend/static/src/scss/backend.scss",
        ],
    },
    "installable": True,
    "application": False,
}
