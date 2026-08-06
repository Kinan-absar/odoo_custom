from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AbsarApprovalEngineMixin(models.AbstractModel):
    _name = 'absar.approval.engine.mixin'
    _description = 'Approval Engine Mixin'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    approval_request_ids = fields.Many2many(
        'absar.approval.request', compute='_compute_approval_summary',
        string='Approval Requests', readonly=True,
    )
    approval_request_id = fields.Many2one(
        'absar.approval.request', compute='_compute_approval_summary', string='Current Approval',
    )
    approval_state = fields.Selection(related='approval_request_id.state', string='Approval Status')
    approval_stage_id = fields.Many2one(related='approval_request_id.stage_id', string='Approval Stage')
    approval_count = fields.Integer(compute='_compute_approval_summary')
    approval_can_approve = fields.Boolean(related='approval_request_id.can_current_user_approve')
    approval_can_reject = fields.Boolean(related='approval_request_id.can_current_user_reject')

    def _compute_approval_summary(self):
        Request = self.env['absar.approval.request']
        for record in self:
            requests = Request.search([
                ('res_model', '=', record._name), ('res_id', '=', record.id),
            ], order='create_date desc, id desc') if record.id else Request.browse()
            record.approval_request_ids = requests
            record.approval_request_id = requests[:1]
            record.approval_count = len(requests)

    def action_request_approval(self):
        for record in self:
            active = record.approval_request_ids.filtered(lambda r: r.state in ('draft', 'in_progress'))
            if active:
                raise UserError(_('An active approval request already exists.'))
            request = self.env['absar.approval.request'].create_for_record(record)
            record._approval_engine_started(request)
        return True

    def action_approval_approve(self):
        self.ensure_one()
        return self.approval_request_id.action_approve()

    def action_approval_reject(self):
        self.ensure_one()
        return self.approval_request_id.action_reject()

    def action_open_approval_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'absar.approval.request',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {'create': False},
        }

    def _approval_engine_started(self, request):
        """Hook called after a request starts. Override in business modules."""
        return True

    def _approval_engine_approved(self, request):
        """Execute the workflow's configured final action."""
        self.ensure_one()
        return request.workflow_id.execute_target_action(self, 'approved')

    def _approval_engine_rejected(self, request, reason):
        """Execute the workflow's configured rejection action."""
        self.ensure_one()
        return request.workflow_id.execute_target_action(self, 'rejected')
