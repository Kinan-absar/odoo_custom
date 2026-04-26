{
    "name": "Internal Transfer & Payment Voucher",
    "version": "19.0.1.1.0",
    "category": "Accounting",
    "summary": "Internal journal transfers, payment vouchers, and receipt vouchers for Odoo 18",
    "description": """
Internal Transfers & Payment Vouchers
=====================================

This module restores and extends internal accounting operations that were simplified in Odoo 18.

Key Features
------------
• Internal Transfers between Bank and Cash journals
• Single journal entry posting (Odoo-native accounting)
• Optional bank fees with VAT support
• Payment Vouchers — outbound payments (Cash / Cheque / Bank Transfer)
• Receipt Vouchers — inbound receipts (Cash / Cheque / Bank Transfer)
• Clean workflow: Draft → Posted → Cancel
• Printable, professional bilingual (English / Arabic) PDF vouchers
• Amount in words (Arabic)
• Optional analytic distribution on expense and income accounts
• Classic accounting-style layouts suitable for real-world printing

Internal Transfer
-----------------
• Transfer between bank and cash journals
• Optional bank fees and VAT
• Automatic balancing journal entry
• Printable internal transfer voucher

Payment Voucher
---------------
• Outgoing payments (Cash / Cheque / Bank Transfer)
• Optional bank fees with VAT and analytic distribution
• Optional analytic on expense/advance account
• Accountant-friendly printable voucher (سند صرف)

Receipt Voucher
---------------
• Incoming receipts from customers (Cash / Cheque / Bank Transfer)
• Optional analytic on income/receivable account
• Accountant-friendly printable voucher (سند قبض)

Designed For
------------
• Middle East accounting practices
• Companies migrating from Odoo 16 / 17 to Odoo 18
• Users who need classic vouchers instead of simplified UI flows

No external dependencies.
Fully compatible with Odoo 18.
""",
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "license": "OPL-1",
    "price": 14.99,
    "currency": "USD",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "report/internal_transfer_report.xml",
        "report/internal_transfer_pdf.xml",
        "report/payment_voucher_report.xml",
        "report/payment_voucher_pdf.xml",
        "report/receipt_voucher_report.xml",
        "report/receipt_voucher_pdf.xml",
        "views/internal_transfer_views.xml",
        "views/payment_voucher_views.xml",
        "views/receipt_voucher_views.xml",
        "views/menus.xml",
    ],
    'assets': {
        'web.assets_backend': [
            'internal_transfer_voucher/static/src/js/payment_voucher_dashboard.js',
            'internal_transfer_voucher/static/src/xml/payment_voucher_dashboard.xml',
        ],
    },
    "images": ["images/main_screenshot.png"],
    "installable": True,
    "application": False,
}
