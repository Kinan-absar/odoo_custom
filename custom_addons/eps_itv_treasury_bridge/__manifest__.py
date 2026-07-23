{
    'name': 'Employee Portal Treasury Bridge',
    'version': '18.0.1.0.3',
    'summary': 'Adds CEO Payment Approvals & Weekly Cash Plans to the Employee Portal, '
                'connecting Employee Portal Suite with the Internal Transfer Voucher app.',
    'description': """
Integration bridge between Employee Portal Suite and Internal Transfer Voucher.

Neither of those two modules requires the other to install or work. Install this
bridge module in addition to both if you want the CEO to review and approve
weekly cash plan payments from inside the Employee Portal.

Adds:
✔ /my/employee/treasury/* portal routes (CEO only)
✔ Payment Approvals & Weekly Cash Plans dashboard cards
✔ Nav links in the portal layout
    """,
    'license': 'LGPL-3',
    'author': 'Kinan',
    'category': 'Human Resources',
    'application': False,
    'installable': True,

    'depends': [
        'employee_portal_suite',
        'internal_transfer_voucher',
    ],

    'data': [
        'views/treasury_templates.xml',
        'views/dashboard_extension.xml',
        'views/layout_extension.xml',
    ],
}
