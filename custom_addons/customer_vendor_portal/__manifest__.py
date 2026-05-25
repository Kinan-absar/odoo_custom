# -*- coding: utf-8 -*-
{
    'name': 'Customer & Vendor Portal Extension',
    'version': '2.0.0',
    'author': 'Kinan',
    'website': 'https://absar-alomran.com',
    'category': 'Portal',
    'summary': 'Professional vendor portal with smart onboarding, invoice tracking, and review comments.',
    'description': """
Customer & Vendor Portal Extension v2
======================================

Redesigned vendor portal with a professional UX for Odoo 18.

Features:
---------
- Smart first-login onboarding: vendors see account details only once, then go directly to dashboard
- Vendor dashboard with live stats (total invoices, amounts by status)
- Beautiful invoice list with status badges and progress tracker
- Invoice detail page with review comments/notes visible to vendor
- Drag-and-drop invoice upload form
- Purchase Order list with detail view
- Bilingual Support (English / Arabic)
""",
    'depends': [
        'portal',
        'website',
        'purchase',
        'sale',
        'account',
        'mail',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/vendor_invoice_sequence.xml',
        'views/vendor_invoice_views.xml',
        'views/portal_vendor_menu.xml',
        'views/portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'customer_vendor_portal/static/src/css/vendor_portal.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
