{
    'name': 'Absar Chat PWA',
    'version': '18.0.1.0.1',
    'summary': 'Standalone company communication PWA powered by Odoo 18 Discuss',
    'description': """
Absar Chat PWA
==============
Standalone, installable Progressive Web Application for internal company communication.
Uses Odoo 18 Discuss as the single source of truth and runs beside Employee Portal Suite.
    """,
    'category': 'Discuss',
    'author': 'Absar / Kinan',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'depends': [
        'base',
        'web',
        'mail',
        'hr',
        'employee_portal_suite',
    ],
    'data': [
        'views/chat_templates.xml',
    ],
    # Deliberately no custom Odoo asset bundle here.  /chat is a standalone PWA
    # and loads its small CSS/JS files directly from /static.  This avoids
    # backend SCSS bundle dependencies and keeps the shell independent from
    # the normal WebClient while still using authenticated Odoo JSON routes.
    'images': ['static/description/icon.png'],
}
