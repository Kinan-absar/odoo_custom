# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ── POS Feature Access Flags ──────────────────────────────────────────────
    pos_allow_payment = fields.Boolean(
        string='Allow Payment',
        default=True,
        help='Allow this user to process payments in POS.',
    )
    pos_allow_discount = fields.Boolean(
        string='Allow Discount',
        default=True,
        help='Allow this user to apply discounts in POS.',
    )
    pos_allow_edit_price = fields.Boolean(
        string='Allow Edit Price',
        default=True,
        help='Allow this user to manually edit product prices in POS.',
    )
    pos_allow_qty = fields.Boolean(
        string='Allow Change Quantity',
        default=True,
        help='Allow this user to change product quantities in POS.',
    )
    pos_allow_remove_line = fields.Boolean(
        string='Allow Remove Order Line',
        default=True,
        help='Allow this user to remove order lines in POS.',
    )
    pos_allow_customer = fields.Boolean(
        string='Allow Customer Selection',
        default=True,
        help='Allow this user to set/change the customer on a POS order.',
    )
    pos_allow_numpad = fields.Boolean(
        string='Allow Numpad',
        default=True,
        help='Allow this user to use the numpad in POS.',
    )
    pos_allow_plus_minus = fields.Boolean(
        string='Allow +/- Button',
        default=True,
        help='Allow this user to use the +/- (increment/decrement) buttons in POS.',
    )
