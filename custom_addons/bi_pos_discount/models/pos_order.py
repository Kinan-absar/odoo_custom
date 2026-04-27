# -*- coding: utf-8 -*-
from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    bi_discount_type = fields.Selection(
        selection=[
            ('percentage', 'Percentage (%)'),
            ('fixed', 'Fixed Amount'),
        ],
        string='Discount Type',
        readonly=True,
    )
    bi_discount_value = fields.Float(
        string='Discount Value',
        readonly=True,
        help='The discount value applied: percentage or fixed amount depending on discount type.',
    )
    bi_discount_amount = fields.Monetary(
        string='Discount Amount',
        readonly=True,
        help='The actual monetary discount amount applied to this order.',
    )

    @api.model
    def _order_fields(self, ui_order):
        """Include our custom discount fields when creating the order from POS."""
        order_fields = super()._order_fields(ui_order)
        order_fields['bi_discount_type'] = ui_order.get('bi_discount_type', False)
        order_fields['bi_discount_value'] = ui_order.get('bi_discount_value', 0.0)
        order_fields['bi_discount_amount'] = ui_order.get('bi_discount_amount', 0.0)
        return order_fields
