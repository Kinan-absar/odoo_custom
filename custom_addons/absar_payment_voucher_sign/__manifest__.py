{
    'name': 'Send to Sign for Payment Vouchers',
    'version': '18.0.1.0.0',
    'author': 'Kinan',
    'license': 'LGPL-3',
    'depends': ['internal_transfer_voucher', 'absar_sign_workflow_core'],
    'data': ['views/payment_voucher_sign_views.xml', 'data/workflow_templates.xml', 'data/cron.xml'],
    'installable': True,
    'application': False,
}
