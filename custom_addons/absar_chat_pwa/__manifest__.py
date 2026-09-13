{
    'name': 'Absar Chat PWA',
    'version': '18.0.2.2.0',
    'summary': 'Installable Absar Chat PWA using the proven native Odoo Discuss route and RTC',
    'description': """
Absar Chat PWA
==============
Installable employee communication PWA powered by the same native Odoo 18 Discuss
frontend, Store, attachments, reactions, replies and RTC stack already used by
Employee Portal Suite. Conversation pages are opened through the exact working
Employee Portal native Discuss route to preserve all existing Discuss behavior.
    """,
    'category': 'Discuss',
    'author': 'Absar / Kinan',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'depends': ['web', 'mail', 'hr', 'employee_portal_suite'],
    'data': ['views/chat_templates.xml'],
    'assets': {
        'mail.assets_public': [
            'absar_chat_pwa/static/src/js/native_discuss_pwa.js',
            'absar_chat_pwa/static/src/css/native_discuss_pwa.css',
        ],
    },
    'images': ['static/description/icon.png'],
}
