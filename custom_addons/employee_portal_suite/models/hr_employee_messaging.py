# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def action_open_employee_portal_message(self):
        self.ensure_one()
        if not self.user_id or not self.user_id.partner_id:
            raise UserError(_('This employee is not linked to a user/partner account.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Employee Message'),
            'res_model': 'employee.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_id': self.id,
                'default_recipient_partner_id': self.user_id.partner_id.id,
            },
        }
