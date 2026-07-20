{
    'name': 'Construction Contract Management - Employee Portal Bridge',
    'version': '18.0.1.0.1',
    'summary': 'Exposes Construction Contract Management (contracts, IPCs, variations, '
                'measurements) inside the Employee Portal Suite portal.',
    'description': """
Integration bridge between Construction Contract Management and Employee Portal Suite.

Neither of those two modules requires the other to install or work. Install this
bridge module in addition to both if you want employees to view/submit
contracts, IPCs, variations, and measurements from the Employee Portal
(/my/employee/...) rather than only the backend.

Adds:
✔ /my/employee/contracts, /ipcs, /variations, /measurements portal routes
✔ Dashboard cards on the Employee Portal home page
    """,
    'category': 'Construction',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'application': False,
    'installable': True,

    'depends': [
        'construction_contract_management',
        'employee_portal_suite',
    ],

    'data': [
        'views/employee_dashboard_extension.xml',
        'views/portal_employee_contract_templates.xml',
        'views/portal_employee_ipc_templates.xml',
        'views/portal_employee_variation_templates.xml',
        'views/portal_employee_measurement_templates.xml',
    ],
}
