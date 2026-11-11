{'name': 'Employee Portal Treasury Bridge',
 'version': '18.0.1.5.1',
 'summary': 'Adds CEO Payment Approvals & Weekly Cash Plans to the Employee Portal, connecting Employee '
            'Portal Suite with the Internal Transfer Voucher app.',
 'description': '\n'
                'Integration bridge between Employee Portal Suite and Internal Transfer Voucher.\n'
                '\n'
                'Neither of those two modules requires the other to install or work. Install this\n'
                'bridge module in addition to both if you want the CEO to review and approve\n'
                'weekly cash plan payments from inside the Employee Portal.\n'
                '\n'
                'Adds:\n'
                '✔ /my/employee/treasury/* portal routes (CEO only)\n'
                '✔ Payment Approvals & Weekly Cash Plans dashboard cards\n'
                '✔ Nav links in the portal layout\n'
                '    ',
 'license': 'LGPL-3',
 'author': 'Kinan',
 'category': 'Human Resources',
 'application': False,
 'installable': True,
 'depends': ['employee_portal_suite', 'internal_transfer_voucher', 'purchase'],
 'data': ['views/treasury_templates.xml', 'views/dashboard_extension.xml', 'views/layout_extension.xml']}
