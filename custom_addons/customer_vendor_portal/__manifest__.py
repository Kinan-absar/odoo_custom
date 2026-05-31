# -*- coding: utf-8 -*-
{
    'name': 'Customer & Vendor Portal Extension',
    'version': '1.0.0',
    'author': 'Kinan',
    'website': 'https://absar-alomran.com',
    'category': 'Portal',
    'summary': 'Enhanced customer portal and new vendor portal with invoice upload, PO access, and financial data.',
    'description': """
Customer & Vendor Portal Extension
==================================

This module extends the default Odoo customer portal with additional features,
and introduces a full vendor portal that allows vendors to view purchase orders,
upload invoices, and track their invoice status.

Features:
---------
- Enhanced Customer Portal (Statements, Invoices, Orders, Documents)
- Full Vendor Portal
- Vendor Purchase Order list and PDF view
- Vendor Invoice Upload
- Vendor Invoice Status Tracking (Submitted, Under Review, Approved, Rejected)
- Bilingual Support (English / Arabic)
""",
    'depends': [
        'portal',
        'website',
        'purchase',
        'sale', 
        'account',
        'mail'
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
            # future CSS/JS for bilingual UI improvements
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
