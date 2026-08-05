# -*- coding: utf-8 -*-
{
    "name": "Aurora Website Theme",
    "summary": "A clean, modern and editable website theme for Odoo 18",
    "description": """
Aurora Website Theme
====================

A deployable Odoo 18 website theme with:

* Aurora color palette and typography
* Website-scoped header, footer, button and card styling
* An editable Feature Cards building block
* Lightweight scroll-in animations with reduced-motion support
* App metadata so the module is easy to locate in the Apps menu
    """,
    "category": "Theme/Creative",
    "version": "18.0.1.1.0",
    "author": "Absar Al Omran",
    "website": "https://absar-alomran.com",
    "license": "LGPL-3",
    "depends": ["website"],
    "data": [
        "views/layout.xml",
        "views/snippets/s_feature_cards.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            "theme_mytheme/static/src/scss/primary_variables.scss",
        ],
        "web.assets_frontend": [
            "theme_mytheme/static/src/scss/theme.scss",
            "theme_mytheme/static/src/js/theme.js",
        ],
    },
    "images": ["static/description/cover.png"],
    "application": True,
    "installable": True,
    "auto_install": False,
    "sequence": 5,
}
