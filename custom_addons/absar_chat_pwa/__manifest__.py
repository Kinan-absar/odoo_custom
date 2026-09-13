# -*- coding: utf-8 -*-
{
    'name': 'Chats PWA',
    'version': '18.0.3.9.0',
    'summary': 'Installable employee Chats app powered by Odoo Discuss',
    'category': 'Discuss',
    'author': 'ABSAR ALOMRAN',
    'license': 'LGPL-3',
    'depends': ['employee_portal_suite', 'mail', 'hr', 'web'],
    'data': ['views/chat_templates.xml'],
    'assets': {
        'web.assets_backend': [
            'absar_chat_pwa/static/src/js/backend_user_menu.js',
        ],
        'mail.assets_public': [
            'absar_chat_pwa/static/src/js/native_rtc_autostart_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
