{
 'name': 'Absar Direct Print', 'version': '18.0.1.0.3',
 'category': 'Productivity', 'summary': 'A separate Print button and Windows office print queue',
 'author': 'Absar Alomran', 'license': 'LGPL-3',
 'depends': ['web'],
 'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/print_views.xml'],
 'assets': {'web.assets_backend': ['absar_direct_print/static/src/print_button.js', 'absar_direct_print/static/src/print_button.xml']},
 'application': True, 'installable': True,
}
