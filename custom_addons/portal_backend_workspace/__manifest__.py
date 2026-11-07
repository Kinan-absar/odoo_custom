{
    'name': 'Portal Backend Workspace — Foundation Prototype',
    'version': '18.0.0.1.0',
    'category': 'Website/Portal',
    'summary': 'Independent portal workspace foundation for Sales, Purchase, Accounting and HR',
    'license': 'OPL-1',
    'depends': ['base', 'web', 'portal', 'website', 'mail'],
    'data': ['security/groups.xml', 'views/workspace.xml'],
    'assets': {'web.assets_frontend': ['portal_backend_workspace/static/src/css/workspace.css']},
    'installable': True,
    'application': True,
}
