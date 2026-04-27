# -*- coding: utf-8 -*-
from odoo import models, api


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def get_pos_ui_pos_disable_payments(self, employee_id):
        """
        Return the access flags for the given employee (or current user).
        Called from the JS layer when an employee logs in / switches.

        Priority:
          1. If the employee has a linked Odoo user → use user flags.
          2. Otherwise → use employee flags.
        """
        employee = self.env['hr.employee'].browse(employee_id)
        user = employee.user_id if employee and employee.user_id else self.env.user

        if user and user.id != self.env.ref('base.public_user').id:
            source = user
        elif employee:
            source = employee
        else:
            # Fallback: allow everything
            return self._all_allowed()

        return {
            'pos_allow_payment':     source.pos_allow_payment,
            'pos_allow_discount':    source.pos_allow_discount,
            'pos_allow_edit_price':  source.pos_allow_edit_price,
            'pos_allow_qty':         source.pos_allow_qty,
            'pos_allow_remove_line': source.pos_allow_remove_line,
            'pos_allow_customer':    source.pos_allow_customer,
            'pos_allow_numpad':      source.pos_allow_numpad,
            'pos_allow_plus_minus':  source.pos_allow_plus_minus,
        }

    def _all_allowed(self):
        return {
            'pos_allow_payment':     True,
            'pos_allow_discount':    True,
            'pos_allow_edit_price':  True,
            'pos_allow_qty':         True,
            'pos_allow_remove_line': True,
            'pos_allow_customer':    True,
            'pos_allow_numpad':      True,
            'pos_allow_plus_minus':  True,
        }
