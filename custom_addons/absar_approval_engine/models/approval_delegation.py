from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AbsarApprovalDelegation(models.Model):
    _name = 'absar.approval.delegation'
    _description = 'Approval Delegation'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    delegator_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, tracking=True, index=True)
    delegate_id = fields.Many2one('res.users', required=True, tracking=True, index=True)
    date_from = fields.Datetime(required=True, default=fields.Datetime.now, tracking=True)
    date_to = fields.Datetime(required=True, tracking=True)
    workflow_ids = fields.Many2many(
        'absar.approval.workflow', 'absar_delegation_workflow_rel', 'delegation_id', 'workflow_id',
        help='Leave empty to delegate all workflows.',
    )
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True, index=True)
    active = fields.Boolean(default=True, tracking=True)
    reason = fields.Text()

    @api.depends('delegator_id', 'delegate_id', 'date_from', 'date_to')
    def _compute_name(self):
        for rec in self:
            rec.name = _('%(delegator)s to %(delegate)s (%(start)s - %(end)s)',
                         delegator=rec.delegator_id.name or '', delegate=rec.delegate_id.name or '',
                         start=rec.date_from or '', end=rec.date_to or '')

    @api.constrains('delegator_id', 'delegate_id', 'date_from', 'date_to')
    def _check_delegation(self):
        for rec in self:
            if rec.delegator_id == rec.delegate_id:
                raise ValidationError(_('You cannot delegate approvals to yourself.'))
            if rec.date_to <= rec.date_from:
                raise ValidationError(_('Delegation end must be after its start.'))

    @api.model
    def delegated_users_for(self, original_users, workflow, at=None):
        at = at or fields.Datetime.now()
        delegations = self.sudo().search([
            ('active', '=', True),
            ('delegator_id', 'in', original_users.ids),
            ('date_from', '<=', at),
            ('date_to', '>=', at),
            ('company_id', 'in', [False, workflow.company_id.id or self.env.company.id]),
        ])
        delegations = delegations.filtered(lambda d: not d.workflow_ids or workflow in d.workflow_ids)
        return delegations.mapped('delegate_id')
