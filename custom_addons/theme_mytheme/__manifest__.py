# -*- coding: utf-8 -*-
{
    'name': 'Aurora Theme',
    'summary': 'A modern, clean, high-contrast theme for the Odoo website',
    'description': """
Aurora Theme
============
A modern website theme for Odoo 18 featuring:
- Custom color palette (deep indigo + amber accent)
- Poppins typography
- Rounded cards, soft shadows, gradient buttons
- Restyled header & footer
- Scroll-triggered fade-in animations
- Custom "Feature Cards" building-block snippet for the website editor
""",
    'category': 'Theme/Creative',
    'version': '1.1',
    'author': 'Your Company',
    'website': 'https://www.example.com',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/layout.xml',
        'views/snippets/s_feature_cards.xml',
    ],
    'assets': {
        # Variables that must be available BEFORE bootstrap/website core SCSS compiles
        'web._assets_primary_variables': [
            'theme_mytheme/static/src/scss/primary_variables.scss',
        ],
        # Regular frontend styling + behaviour
        'web.assets_frontend': [
            'theme_mytheme/static/src/scss/theme.scss',
            'theme_mytheme/static/src/js/theme.js',
        ],
    },
    'images': [
        'static/description/cover.png',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
