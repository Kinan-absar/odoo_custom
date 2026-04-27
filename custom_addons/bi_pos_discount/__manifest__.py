# -*- coding: utf-8 -*-
{
    'name': 'POS Discount – Fixed Amount & Percentage',
    'version': '18.0.0.1',
    'summary': 'Apply fixed amount or percentage discounts on POS orders. Discount is shown on receipt and recorded in the backend.',
    'description': """
        Allows POS users to apply a global discount (fixed amount or percentage)
        on the entire POS order directly from the POS screen.
        The discount appears on the printed receipt and in the backend order view.
    """,
    'category': 'Point of Sale',
    'author': 'Custom',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'bi_pos_discount/static/src/js/bi_pos_discount.js',
            'bi_pos_discount/static/src/xml/bi_pos_discount.xml',
            'bi_pos_discount/static/src/css/bi_pos_discount.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
