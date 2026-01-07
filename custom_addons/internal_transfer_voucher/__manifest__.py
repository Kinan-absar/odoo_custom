{
    "name": "Internal Transfer & Payment Voucher",
    "version": "18.0.1.0.0",
    "category": "Accounting",
    "summary": "Internal journal transfers and payment vouchers for Odoo 18",
    "description": """
Reintroduces internal transfers and payment vouchers removed in Odoo 18.

Features:
- Internal transfers between cash/bank journals
- Payment vouchers for advances, expenses, and payments
- Clean accounting entries
- Printable professional vouchers
""",
    "author": "Your Company",
    "website": "https://www.yourcompany.com",
    "license": "OPL-1",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/internal_transfer_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
}
