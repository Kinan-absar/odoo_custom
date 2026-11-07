from odoo import fields, models


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    employee_request_id = fields.Many2one(
        'employee.request',
        string='Employee Request',
        readonly=True,
        copy=False,
        index=True,
        ondelete='set null',
    )

    def action_open_employee_request(self):
        self.ensure_one()
        if not self.employee_request_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': 'Employee Request',
            'res_model': 'employee.request',
            'view_mode': 'form',
            'res_id': self.employee_request_id.id,
            'target': 'current',
        }
