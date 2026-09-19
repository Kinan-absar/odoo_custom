# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.3.0.0",
    "category": "Accounting",
    "summary": "Native Partner-Ledger-style customer and vendor account statements",
    "description": """
        Native Odoo 18 Account Statement Reports built on the Accounting
        Report / Partner Ledger engine.

        Main features:
        - Native editable Odoo accounting-report filter bar
        - Search/select one or multiple customer/vendor partners
        - Editable date range and quick Odoo date periods
        - Journal filtering
        - Receivable / Payable / Both account-type filter
        - Posted entries / draft entries support
        - Unreconciled/open-item filter
        - Multi-company selector
        - Search and unfold/fold controls
        - Native PDF and XLSX export
        - Click-through journal items / source entries
        - Customer and Vendor statement smart buttons on partner form
        - Separate receivable and payable balance indicators

        The previous custom generated statement records are kept in the
        module for backward compatibility, while the main Reporting menu
        now opens the native Odoo report experience.
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "depends": ["account", "account_reports"],
    "data": [
        "security/ir.model.access.csv",
        "views/native_statement_report.xml",
        "views/res_partner_views.xml",
        "views/statement_line_views.xml",
        "report/reports.xml",
        "report/customer_statement.xml",
        "report/vendor_statement.xml",
    ],
    "installable": True,
    "application": False,
    "license": "OPL-1",
}
