{
 'name': 'ABSAR Portal Purchase Monitoring & RFQ Preparation',
 'version': '18.0.1.2.0', 'category': 'Purchases',
 'summary': 'Purchase monitoring plus controlled RFQ preparation and review in Employee Portal',
 'author': 'ABSAR Al Omran Construction Company', 'license': 'LGPL-3',
 'depends': ['employee_portal_suite', 'purchase', 'account', 'mail', 'analytic', 'project'],
 'data': ['security/groups.xml', 'views/purchase_order_views.xml', 'views/portal_purchase_templates.xml', 'views/portal_navigation.xml', 'views/portal_purchase_prepare.xml'],
 'assets': {'web.assets_frontend': ['absar_portal_purchase_monitor/static/src/css/purchase_monitor.css']},
 'installable': True, 'application': False,
}