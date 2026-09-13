# -*- coding: utf-8 -*-
{
    'name': 'Chats PWA',
    'version': '18.0.3.8.0',
    'summary': 'Installable employee Chats app powered by Odoo Discuss',
    'category': 'Discuss',
    'author': 'ABSAR ALOMRAN',
    'license': 'LGPL-3',
    'depends': ['employee_portal_suite', 'mail', 'hr', 'web'],
    'data': ['views/backend_menu.xml', 'views/chat_templates.xml'],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
}
