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
