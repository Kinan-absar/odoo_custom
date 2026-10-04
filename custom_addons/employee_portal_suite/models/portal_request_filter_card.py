from odoo import fields, models


class EmployeePortalRequestFilterCard(models.Model):
    _name = 'employee.portal.request.filter.card'
    _description = 'Employee Portal Request Filter Card'
    _order = 'request_area, sequence, id'

    name = fields.Char(string='Label', required=True, translate=True)
    request_area = fields.Selection([
        ('employee_request', 'Employee Requests'),
        ('material_request', 'Material Requests'),
    ], string='Request List', required=True, index=True)
    filter_key = fields.Selection([
        ('pending', 'Pending / To Approve'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('all', 'All'),
    ], string='Filter', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('request_area_filter_unique', 'unique(request_area, filter_key)',
         'Each filter can only be configured once per request list.'),
    ]
