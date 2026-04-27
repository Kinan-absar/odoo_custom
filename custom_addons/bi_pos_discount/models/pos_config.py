# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    bi_discount_type = fields.Selection(
        selection=[
            ('percentage', 'Percentage (%)'),
            ('fixed', 'Fixed Amount'),
        ],
        string='Discount Type',
        default='percentage',
        required=True,
        help='Choose whether the POS discount button applies a percentage or a fixed amount discount.',
    )
    bi_discount_value = fields.Float(
        string='Default Discount Value',
        default=0.0,
        help='Pre-filled default value shown on the discount dialog (0 = no default).',
    )
    bi_show_discount_button = fields.Boolean(
        string='Show Discount Button in POS',
        default=True,
        help='Show or hide the custom discount button on the POS order screen.',
    )
