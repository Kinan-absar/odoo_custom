# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.2.0.0",
    "category": "Accounting",
    "summary": "Customer & Vendor Statements with Filters, Running Balance, PDF and Excel",
    "description": """
        Financial statements for customers and vendors:
        - Opening balance
        - Running balance
        - Clean PDF report (Customer & Vendor)
        - Excel export
        - Statement wizards with company, journal and account filters
        - Posted/draft entry selection
        - Optional opening balance
        - Direct PDF and Excel export from the wizard
        - Refreshable statement review with journal entry links
        - Multi-company safe calculations
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "depends": ["account"],

    "data": [
        # Security
        "security/ir.model.access.csv",

        # Views (menus, wizards, statement forms)
        "views/statement_views.xml",
        "views/statement_line_views.xml",
        'views/res_partner_views.xml',

        # Reports
        "report/reports.xml",
        "report/customer_statement.xml",
        "report/vendor_statement.xml",
    ],

    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
