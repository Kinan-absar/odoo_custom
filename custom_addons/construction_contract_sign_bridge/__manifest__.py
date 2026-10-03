{
    "name": "Construction Contract Send to Sign Bridge",
    "version": "18.0.1.1.2",
    "summary": "Configurable Odoo Sign workflows for Contracts, Measurements and IPCs",
    "description": """
Bridge between Construction Contract Management and ABSAR Sign Workflow Core.
Adds configurable signer chains, dynamic signing status and revision tracking to
Construction Contracts, Measurements and IPCs.
    """,
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "category": "Construction",
    "license": "LGPL-3",
    "depends": [
        "construction_contract_management",
        "absar_sign_workflow_core"
    ],
    "data": [
        "data/cron.xml",
        "views/construction_sign_views.xml",
        "reports/construction_sign_report.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
