# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.8.0.0",
    "category": "Accounting",
    "summary": "Customer & Vendor Statements with Editable Filters, Running Balance, PDF and Excel",
    "description": """
        Financial statements for customers and vendors:
        - Editable partner, company, date, journal, account and entry-state filters directly on the statement
        - Apply Filters button to refresh the same statement without returning to the wizard
        - Opening balance and running balance
        - Clean Customer & Vendor PDF reports
        - Excel export
        - Optional opening balance
        - Clickable journal entry links
        - Multi-company safe calculations
        - Styled statement workspace with balance and transaction summary cards
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
        "report/customer_statement.xml",
        "report/vendor_statement.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "account_statement_reports/static/src/scss/statement_views.scss",
        ],
    },

    "installable": True,
    "application": False,
    "license": "OPL-1",
}
