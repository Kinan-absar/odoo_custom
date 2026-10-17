{
    'name': 'ABSAR Portal Sales - Employee Bell Bridge',
    'version': '18.0.1.0.1',
    'category': 'Sales',
    'summary': 'Sales review notifications in the existing Employee Portal bell',
    'author': 'ABSAR Al Omran Construction Company',
    'license': 'LGPL-3',
    'depends': ['absar_portal_sales', 'employee_portal_suite'],
    'data': ['security/ir.model.access.csv','views/bell_views.xml'],
    'installable': True,
    'application': False,
}
