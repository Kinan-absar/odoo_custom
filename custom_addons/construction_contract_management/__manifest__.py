{
    'name': 'Construction Contract Management',
    'version': '18.0.1.0.0',
    'summary': 'Dual-mode construction contract and subcontract management',
    'description': """
Construction Contract Management

- Inbound / Outbound contracts
- BOQ
- Measurements
- IPC
- Construction workflow engine
    """,
    'category': 'Construction',
    'author': 'Your Company',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'project',
        'account',
        'uom',
    ],
    'data': [
        'security/construction_security.xml',
        'security/ir.model.access.csv',

        'views/construction_sequence.xml',

        'views/construction_contract_views.xml',
        'views/construction_measurement_views.xml',
        'views/construction_ipc_views.xml',
        'views/construction_menus.xml',
    ],
    'application': True,
    'installable': True,
}