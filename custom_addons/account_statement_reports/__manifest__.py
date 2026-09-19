# -*- coding: utf-8 -*-
{
    "name": "Account Statement Reports",
    "version": "18.0.4.0.0",
    "category": "Accounting",
    "summary": "Native Partner-Ledger-style customer and vendor account statements",
    "description": """
        Native Odoo 18 Account Statement Reports built as a dedicated
        Accounting Report variant using the Partner Ledger engine.

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

        The previous custom generated statement records are kept for backward
        compatibility. The main Reporting menu now opens a dedicated
        Account Statement Reports record instead of the original Partner Ledger.
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
