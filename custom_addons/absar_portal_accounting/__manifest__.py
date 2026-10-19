{
    'name': 'ABSAR Employee Portal Accounting',
    'version': '18.0.1.2.0',
    'summary': 'Vendor bills, journal entries, vouchers and cash planning in the employee portal',
    'author': 'Kinan',
    'license': 'LGPL-3',
    'depends': ['employee_portal_suite', 'internal_transfer_voucher', 'purchase'],
    'data': ['security/groups.xml', 'security/ir.model.access.csv', 'views/post_confirmation.xml', 'views/configuration.xml', 'views/report.xml', 'views/portal.xml'],
    'assets': {'web.assets_frontend': [
        'absar_portal_accounting/static/src/accounting.css',
        'absar_portal_accounting/static/src/accounting.js',
    ]},
    'installable': True,
    'application': False,
}
