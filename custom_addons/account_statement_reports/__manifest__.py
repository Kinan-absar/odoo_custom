# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.7.0.0",
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
        - Extra Statement PDF and Statement Excel buttons on the native Odoo Partner Ledger
        - Statement export reuses the active Partner Ledger partner/date/journal/company/status filters
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "depends": ["account", "account_reports"],

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
        "report/partner_ledger_statement.xml",
    ],

    "installable": True,
    "application": False,
    "license": "OPL-1",
}
