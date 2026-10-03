from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class EmployeePortalRoleAssignment(models.Model):
    _name = 'employee.portal.role.assignment'
    _description = 'Employee Portal Role Assignment'
    _order = 'section_sequence, sequence, name'

    name = fields.Char(required=True, readonly=True)
    section = fields.Selection([
        ('approval', 'Employee Request Roles'),
        ('material', 'Material Request Roles'),
        ('administration', 'Administration'),
        ('communication', 'Communication'),
        ('attendance', 'Attendance'),
        ('reports', 'Reports'),
    ], required=True, readonly=True)
    section_sequence = fields.Integer(default=10, readonly=True)
    sequence = fields.Integer(default=10, readonly=True)
    group_xmlid = fields.Char(required=True, readonly=True)
    description = fields.Char(readonly=True)
    user_ids = fields.Many2many(
        'res.users',
        string='Users',
        compute='_compute_user_ids',
        inverse='_inverse_user_ids',
        readonly=False,
    )
    user_count = fields.Integer(compute='_compute_user_count', string='Users')

    def _check_superadmin(self):
        if not self.env.user.has_group('employee_portal_suite.group_employee_portal_superadmin'):
            raise AccessError(_('Only an Employee Portal Super Administrator can manage roles and permissions.'))

    def _group(self):
        self.ensure_one()
        return self.env.ref(self.group_xmlid, raise_if_not_found=False)

    @api.depends('group_xmlid')
    def _compute_user_ids(self):
        for rec in self:
            group = rec._group()
            rec.user_ids = group.sudo().users if group else False

    @api.depends('user_ids')
    def _compute_user_count(self):
        for rec in self:
            rec.user_count = len(rec.user_ids)

    def _inverse_user_ids(self):
        self._check_superadmin()
        for rec in self:
            group = rec._group()
            if not group:
                continue
            # Roles are intentionally independent. In particular, Super
            # Administrator does not imply or force Administrator membership.
            group.sudo().write({'users': [(6, 0, rec.user_ids.sudo().ids)]})
