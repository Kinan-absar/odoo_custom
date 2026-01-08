{
    "name": "Internal Transfer & Payment Voucher",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Internal journal transfers and payment vouchers for Odoo 18",
    "description": """
Internal Transfers & Payment Vouchers
=====================================

This module restores and extends internal accounting operations that were simplified in Odoo 18.

Key Features
------------
• Internal Transfers between Bank and Cash journals  
• Single journal entry posting (Odoo-native accounting)  
• Optional bank fees with VAT support  
• Payment Vouchers (Outbound only)  
• Clean workflow: Draft → Posted → Cancel  
• Printable, professional bilingual (English / Arabic) PDF vouchers  
• Amount in words (Arabic)  
• Classic accounting-style layouts suitable for real-world printing  

Internal Transfer
-----------------
• Transfer between bank and cash journals  
• Optional bank fees and VAT  
• Automatic balancing journal entry  
• Printable internal transfer voucher  

Payment Voucher
---------------
• Outgoing payments only (Cash / Cheque)  
• Simple accounting posting  
• No VAT, no analytic complexity  
• Designed for petty cash and manual payments  
• Accountant-friendly printable voucher  

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
        "views/internal_transfer_views.xml",
        "views/payment_voucher_views.xml",
        "views/menus.xml",

    ],
    "images": ["images/main_screenshot.png"],
    "installable": True,
    "application": False,
}
