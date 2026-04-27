{
    "name": "Internal Transfer & Payment Voucher",
    "version": "19.0.1.1.0",
    "category": "Accounting",
    "summary": "Internal journal transfers, payment vouchers, and receipt vouchers for Odoo 19",
    "description": """
Internal Transfers & Payment Vouchers
=====================================

Key Features
------------
• Internal Transfers between Bank and Cash journals
• Payment Vouchers — outbound payments (Cash / Cheque / Bank Transfer)
• Receipt Vouchers — inbound receipts (Cash / Cheque / Bank Transfer)
• Dashboard on Payment Voucher and Receipt Voucher list views
• Clean workflow: Draft → Posted → Cancel
• Printable bilingual (English / Arabic) PDF vouchers
• Amount in words (Arabic)
• Optional analytic distribution
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
            'internal_transfer_voucher/static/src/scss/payment_voucher_dashboard.scss',
            'internal_transfer_voucher/static/src/js/receipt_voucher_dashboard.js',
            'internal_transfer_voucher/static/src/xml/receipt_voucher_dashboard.xml',
            'internal_transfer_voucher/static/src/scss/receipt_voucher_dashboard.scss',
        ],
    },
    "images": ["images/main_screenshot.png"],
    "installable": True,
    "application": False,
}
