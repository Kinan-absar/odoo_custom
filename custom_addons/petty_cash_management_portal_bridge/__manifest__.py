{'name': 'Petty Cash Management - Employee Portal Bridge',
 'version': '18.0.1.2.6',
 'summary': 'Exposes Petty Cash Management inside the Employee Portal Suite portal.',
 'description': '\n'
                'Integration bridge between Petty Cash Management and Employee Portal Suite.\n'
                '\n'
                'Neither of those two modules requires the other to install or work. Install this\n'
                'bridge module in addition to both if you want employees to submit/view petty\n'
                'cash reports from the Employee Portal (/my/employee/petty-cash) rather than\n'
                'only the backend.\n'
                '    ',
 'category': 'Accounting',
 'author': 'Kinan',
 'license': 'OPL-1',
 'application': False,
 'installable': True,
 'depends': ['petty_cash_management', 'employee_portal_suite', 'portal', 'website'],
 'data': ['views/layout_extension.xml', 'views/portal_petty_cash_templates.xml']}
