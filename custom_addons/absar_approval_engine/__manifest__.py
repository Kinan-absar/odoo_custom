{
    'name': 'Absar Approval Engine',
    'version': '18.0.1.0.1',
    'category': 'Productivity/Approvals',
    'summary': 'Reusable configurable multi-stage approval engine for any Odoo model',
    'description': """
Absar Approval Engine
=====================
A reusable, multi-company approval framework for Odoo 18. It provides
configurable workflows and stages, user/group/record-field approvers,
delegation, deadlines, mail activities, immutable audit history, and an
abstract mixin that other business modules can inherit.
    """,
    'author': 'Absar Alomran',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/approval_security.xml',
        'security/ir.model.access.csv',
        'data/approval_data.xml',
        'data/approval_cron.xml',
        'views/approval_workflow_views.xml',
        'views/approval_request_views.xml',
        'views/approval_delegation_views.xml',
        'views/approval_audit_views.xml',
        'views/approval_menus.xml',
    ],
    'application': True,
    'installable': True,
}
