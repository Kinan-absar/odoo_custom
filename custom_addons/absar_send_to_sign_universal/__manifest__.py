{
    'name': 'ABSAR Universal Send to Sign',
    'version': '18.0.1.0.0',
    'summary': 'Configure Send to Sign for business models without per-model bridges',
    'author': 'Kinan', 'website': 'https://absar-alomran.com',
    'category': 'Productivity/Documents', 'license': 'LGPL-3',
    'depends': ['absar_sign_workflow_core'],
    'data': ['security/ir.model.access.csv', 'security/rules.xml',
             'views/integration_views.xml', 'views/document_views.xml', 'views/workflow_views.xml'],
    'installable': True, 'application': False,
}
