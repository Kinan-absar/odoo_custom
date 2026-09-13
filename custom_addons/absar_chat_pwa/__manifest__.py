{
    'name': 'Absar Chat PWA',
    'version': '18.0.1.0.0',
    'summary': 'Standalone Company Communication PWA powered by Odoo 18 Discuss',
    'description': """
Absar Chat PWA
==============
Standalone, installable Progressive Web Application for internal company communication.
Directly integrated with native Odoo 18 Discuss and Employee Portal Suite.

Key Highlights:
- Single source of truth: discuss.channel, discuss.channel.member, mail.message.
- Real-time synchronization between Absar Chat and standard Odoo Discuss.
- Zero duplication of conversations or messages.
- Full-screen modern PWA shell at /chat with zero portal chrome.
- Strictly restricted to authenticated active employees.
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
    'assets': {
        'absar_chat_pwa.assets_chat': [
            # Core Odoo web & bus utilities
            ('include', 'web._assets_helpers'),
            ('include', 'web._assets_backend_helpers'),
            'web/static/src/scss/pre_variables.scss',
            'web/static/lib/bootstrap/scss/_variables.scss',
            ('include', 'web._assets_bootstrap_backend'),
            ('include', 'web._assets_core'),
            # Absar Chat custom PWA styling & components
            'absar_chat_pwa/static/src/scss/absar_chat.scss',
            'absar_chat_pwa/static/src/js/absar_chat_app.js',
            'absar_chat_pwa/static/src/xml/absar_chat_app.xml',
        ],
    },
    'images': ['static/description/icon.png'],
}
