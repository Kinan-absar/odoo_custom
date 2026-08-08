{
    'name': 'SharePoint Accounting Archive',
    'version': '18.0.1.2.0',
    'category': 'Accounting/Accounting',
    'summary': 'Archive posted accounting entries and attachments to Microsoft SharePoint',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'report/journal_voucher_report.xml',
        'views/sharepoint_historical_archive_wizard_views.xml',
        'views/sharepoint_archive_config_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}
