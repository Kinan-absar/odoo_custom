{
    "name": "Excel Report Builder",
    "summary": "No-code reusable XLSX reports from any Odoo model",
    "version": "18.0.1.0.0",
    "category": "Reporting",
    "author": "ABSAR",
    "license": "OPL-1",
    "depends": ["base", "web"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/excel_report_template_views.xml",
        "views/excel_report_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "application": True,
    "installable": True,
}
