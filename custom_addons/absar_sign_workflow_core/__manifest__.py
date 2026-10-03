{
    "name": "ABSAR Sign Workflow Core",
    "version": "18.0.1.0.4",
    "summary": "Reusable configurable signing workflows for Odoo Sign documents",
    "author": "Kinan",
    "website": "https://absar-alomran.com",
    "category": "Productivity/Documents",
    "license": "LGPL-3",
    "depends": ["base", "mail", "sign", "project"],
    "data": [
        "security/ir.model.access.csv",
        "views/sign_workflow_views.xml",
        "data_menu_relocation.xml"
    ],
    "installable": True,
    "application": False,
}
