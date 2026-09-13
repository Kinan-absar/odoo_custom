{
    'name': 'Absar Chat PWA',
    'version': '18.0.2.1.0',
    'summary': 'Installable Absar Chat PWA using native Odoo Discuss and RTC',
    'description': """
Absar Chat PWA
==============
Installable employee communication PWA powered by the same native Odoo 18 Discuss
frontend, Store, attachments, reactions, replies and RTC stack already used by
Employee Portal Suite.
    """,
    'category': 'Discuss',
    'author': 'Absar / Kinan',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'depends': ['web', 'mail', 'hr', 'employee_portal_suite'],
    'data': ['views/chat_templates.xml'],
    'images': ['static/description/icon.png'],
}
