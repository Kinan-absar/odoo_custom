# -*- coding: utf-8 -*-
{
    'name': 'POS Disable / Allow Features (Payments, Discount, Price, Qty...)',
    'version': '18.0.0.1',
    'summary': 'Restrict POS features per user or employee: payment, discount, price, qty, numpad, order line removal, customer selection, +/- button.',
    'description': """
        Allow or deny POS features like Payments, Discount, Quantity,
        Edit Price, Remove Order Line, Customer Selection, Numpad, +/- Button
        for specific POS users and employees.
    """,
    'category': 'Point of Sale',
    'author': 'Custom',
    'depends': ['point_of_sale', 'hr', 'pos_restaurant'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/hr_employee_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_disable_payments/static/src/js/pos_disable_payments.js',
            'pos_disable_payments/static/src/xml/pos_disable_payments.xml',
            'pos_disable_payments/static/src/css/pos_disable_payments.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
