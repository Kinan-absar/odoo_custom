from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ApprovalFlowMixin(models.AbstractModel):
    _name = 'approval.flow.mixin'
    _description = 'Approval Flow Mixin'

    state = fields.Selection([], default='draft')  # overridden in child models

    # Helper to stamp approvals
    def _approval_stamp(self, user_field, date_field):
        for rec in self:
            rec[user_field] = self.env.user.id
            rec[date_field] = fields.Datetime.now()

    # Universal reject
    def action_reject(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_("Approved records cannot be rejected."))
            rec.state = 'rejected'
