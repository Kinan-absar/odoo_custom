# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "1.0",
    "category": "Accounting",
    "summary": "Customer and Vendor Financial Statements with Running Balance and Excel Export",
    "description": """
        Financial statements for customers and vendors:
        - Opening balance
        - Running balance
        - Clean PDF report (Customer & Vendor)
        - Excel export
        - Statement wizards
        - Form views for statement review
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

        # Reports
        "report/reports.xml",
        "report/customer_statement.xml",
        "report/vendor_statement.xml",
    ],

    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
