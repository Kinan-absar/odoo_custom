# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.20.0.0",
    "category": "Accounting",
    "summary": "Full-screen receivable and payable account statements with editable filters, PDF and Excel",
    "description": """
        Account statement workspace for Odoo 18:
        - One full-screen Account Statements workspace
        - Customer and Vendor statements in the same screen
        - No popup wizard: filters are edited directly on the report page
        - Searchable partner, date, company, journal, account and entry-state filters
        - Opening balance, debit, credit, transaction and final-balance summaries
        - Clickable journal entries
        - PDF and Excel export
        - Multi-company safe calculations
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "depends": ["account", "account_reports"],
    "data": [
        "security/ir.model.access.csv",
        "views/statement_views.xml",
        "views/statement_line_views.xml",
        "views/res_partner_views.xml",
        "report/reports.xml",
        "report/account_statement.xml",
        "report/customer_statement.xml",
        "report/vendor_statement.xml",
    ],
    "images": ["images/main_screenshot.png"],
    "assets": {
        "web.assets_backend": [
            "account_statement_reports/static/src/scss/statement_views.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
