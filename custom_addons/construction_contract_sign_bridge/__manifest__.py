{
    "name": "Construction Contract Send to Sign Bridge",
    "version": "18.0.1.0.0",
    "summary": "Send Construction Contracts, Measurements and IPCs to Odoo Sign",
    "description": """
Bridge between Construction Contract Management and Send to Sign for Purchase Orders.
Adds the same Odoo Sign workflow, signature status and revision tracking to
Construction Contracts, Measurements and IPCs without adding a Sign dependency
to the base construction module.
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "category": "Construction",
    "license": "LGPL-3",
    "depends": [
        "construction_contract_management",
        "absar_send_to_sign_po",
    ],
    "data": [
        "data/cron.xml",
        "views/construction_sign_views.xml",
        "reports/construction_sign_report.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
