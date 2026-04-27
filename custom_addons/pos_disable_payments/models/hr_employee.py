# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # ── POS Feature Access Flags ──────────────────────────────────────────────
    # These are used only when the employee has no related Odoo user.
    # When a user IS linked, the user's flags take precedence.
    pos_allow_payment = fields.Boolean(
        string='Allow Payment',
        default=True,
        help='Allow this employee to process payments in POS.',
    )
    pos_allow_discount = fields.Boolean(
        string='Allow Discount',
        default=True,
        help='Allow this employee to apply discounts in POS.',
    )
    pos_allow_edit_price = fields.Boolean(
        string='Allow Edit Price',
        default=True,
        help='Allow this employee to manually edit product prices in POS.',
    )
    pos_allow_qty = fields.Boolean(
        string='Allow Change Quantity',
        default=True,
        help='Allow this employee to change product quantities in POS.',
    )
    pos_allow_remove_line = fields.Boolean(
        string='Allow Remove Order Line',
        default=True,
        help='Allow this employee to remove order lines in POS.',
    )
    pos_allow_customer = fields.Boolean(
        string='Allow Customer Selection',
        default=True,
        help='Allow this employee to set/change the customer on a POS order.',
    )
    pos_allow_numpad = fields.Boolean(
        string='Allow Numpad',
        default=True,
        help='Allow this employee to use the numpad in POS.',
    )
    pos_allow_plus_minus = fields.Boolean(
        string='Allow +/- Button',
        default=True,
        help='Allow this employee to use the +/- buttons in POS.',
    )
