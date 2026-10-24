from odoo import models, fields, _
from odoo.exceptions import AccessError

class EmployeeAdminAudit(models.Model):
    _name='absar.employee.admin.audit'
    _description='Employee Admin Portal Audit'
    _order='id desc'
    _rec_name='operation'
    actor_id=fields.Many2one('res.users',required=True,readonly=True)
    company_id=fields.Many2one('res.company',required=True,readonly=True,index=True)
    resource=fields.Char(required=True,readonly=True)
    resource_id=fields.Integer(required=True,readonly=True)
    operation=fields.Char(required=True,readonly=True)
    detail=fields.Text(readonly=True)
    def write(self, vals):
        raise AccessError(_('Employee Admin audit records cannot be changed.'))
    def unlink(self):
        raise AccessError(_('Employee Admin audit records cannot be deleted.'))
