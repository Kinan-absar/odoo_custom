{
    'name': 'Send to Sign for Payment Vouchers',
    'version': '18.0.1.0.3',
    'author': 'Kinan',
    'license': 'LGPL-3',
    'depends': ['internal_transfer_voucher', 'absar_sign_workflow_core'],
    'data': ['security/ir.model.access.csv', 'views/sign_recipient_views.xml',
             'views/payment_voucher_sign_views.xml', 'data/direct_signing_upgrade.xml'],
    'installable': True,
    'application': False,
}
