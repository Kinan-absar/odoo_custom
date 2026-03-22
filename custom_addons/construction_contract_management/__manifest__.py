{
    'name': 'Construction Contract Management',
    'version': '18.0.1.0.0',
    'summary': 'Dual-mode construction contract and subcontract management',
    'description': """
Construction Contract Management

- Inbound / Outbound contracts
- BOQ
- Measurements
- IPC
- Variations
- Construction workflow engine
    """,
    'category': 'Construction',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'account',
        'uom',
        'portal',
    ],
    'data': [
        'security/construction_security.xml',
        'security/construction_portal_security.xml',
        'security/ir.model.access.csv',
        'security/construction_portal_rules.xml',
        'data/construction_dashboard_data.xml',
        'views/construction_sequence.xml',
        'views/construction_dashboard_views.xml',
        'views/construction_contract_views.xml',
        'views/construction_measurement_views.xml',
        'views/construction_ipc_views.xml',
        'views/construction_variation_views.xml',
        'views/construction_advance_views.xml',
        'views/construction_retention_release_views.xml',
        'views/construction_menus.xml',
        'views/portal/employee_dashboard_extension.xml',
        'views/portal/portal_employee_contract_templates.xml',
        'reports/report_actions.xml',
        'reports/construction_ipc_report.xml',
        'reports/construction_variation_report.xml',
        'reports/construction_advance_report.xml',
        'reports/construction_retention_release_report.xml',
    ],
    'application': True,
    'installable': True,
}