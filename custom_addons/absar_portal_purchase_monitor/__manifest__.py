{
 'name': 'ABSAR Portal Purchase Monitoring',
 'version': '18.0.1.0.0',
 'category': 'Purchases',
 'summary': 'Read-only purchase order monitoring in ABSAR Employee Portal',
 'author': 'ABSAR Al Omran Construction Company',
 'license': 'LGPL-3',
 'depends': ['employee_portal_suite', 'purchase', 'account'],
 'data': ['security/groups.xml', 'views/portal_purchase_templates.xml', 'views/portal_navigation.xml'],
 'assets': {'web.assets_frontend': ['absar_portal_purchase_monitor/static/src/css/purchase_monitor.css']},
 'installable': True,
 'application': False,
}
