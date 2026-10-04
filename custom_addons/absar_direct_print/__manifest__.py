{
 'name': 'Absar Direct Print', 'version': '18.0.1.0.0',
 'category': 'Productivity', 'summary': 'Browser printing and a Windows office print queue',
 'author': 'Absar Alomran', 'license': 'LGPL-3',
 'depends': ['web'],
 'data': ['security/security.xml', 'security/ir.model.access.csv', 'views/print_views.xml'],
 'assets': {'web.assets_backend': ['absar_direct_print/static/src/print_handler.js']},
 'application': True, 'installable': True,
}
