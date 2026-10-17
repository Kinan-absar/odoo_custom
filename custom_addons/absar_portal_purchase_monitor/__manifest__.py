{
    'name': 'ABSAR Portal Purchase Workspace',
    'version': '18.0.1.3.0',
    'category': 'Purchases',
    'summary': 'Controlled employee RFQ preparation, review and purchase monitoring',
    'author': 'ABSAR Al Omran Construction Company',
    'license': 'LGPL-3',
    'depends': ['employee_portal_suite', 'purchase_stock', 'account', 'mail', 'analytic', 'project'],
    'data': ['security/groups.xml', 'views/purchase_order_views.xml',
             'views/portal_purchase_templates.xml', 'views/portal_navigation.xml',
             'views/portal_purchase_prepare.xml'],
    'assets': {'web.assets_frontend': [
        'absar_portal_purchase_monitor/static/src/css/purchase_monitor.css',
        'absar_portal_purchase_monitor/static/src/js/purchase_workspace.js',
    ]},
    'installable': True,
    'application': False,
}
