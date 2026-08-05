from odoo import _, fields, models
from odoo.exceptions import AccessError


class AbsarApprovalAudit(models.Model):
    _name = 'absar.approval.audit'
    _description = 'Approval Audit Log'
    _order = 'action_date desc, id desc'
    _rec_name = 'action'

    request_id = fields.Many2one('absar.approval.request', required=True, ondelete='cascade', index=True)
    workflow_id = fields.Many2one(related='request_id.workflow_id', store=True, index=True)
    stage_id = fields.Many2one('absar.approval.stage', ondelete='set null', index=True)
    action = fields.Selection([
        ('started', 'Started'),
        ('stage_started', 'Stage Started'),
        ('approved', 'Approved'),
        ('stage_approved', 'Stage Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('cancelled', 'Cancelled'),
        ('reset', 'Reset'),
        ('delegated', 'Delegated Approval'),
        ('overdue', 'Marked Overdue'),
    ], required=True, index=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, index=True)
    action_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    old_state = fields.Char()
    new_state = fields.Char()
    comment = fields.Text()
    source = fields.Selection([('backend', 'Backend'), ('portal', 'Portal'), ('system', 'System'), ('api', 'API')], default='backend')
    delegated_from_id = fields.Many2one('res.users')
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)

    def write(self, vals):
        raise AccessError(_('Approval audit records are immutable.'))

    def unlink(self):
        raise AccessError(_('Approval audit records cannot be deleted.'))
