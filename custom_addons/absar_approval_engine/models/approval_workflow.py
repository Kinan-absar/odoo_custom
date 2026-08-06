from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class AbsarApprovalWorkflow(models.Model):
    _name = 'absar.approval.workflow'
    _description = 'Approval Workflow'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        'ir.model', required=True, ondelete='cascade', index=True,
        domain=[('transient', '=', False)],
    )
    model = fields.Char(related='model_id.model', store=True, index=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, index=True,
        help='Leave empty to make the workflow available to all companies.',
    )
    domain = fields.Char(
        default='[]', required=True,
        help='Python domain evaluated on the target record. Example: [("amount_total", ">", 10000)]',
    )
    auto_start = fields.Boolean(
        help='Integration modules can use this flag to start approval automatically.',
    )
    requester_can_approve = fields.Boolean(
        help='Allow the user who started the request to approve it when also eligible.',
    )
    allow_withdraw = fields.Boolean(default=True)
    restart_policy = fields.Selection([
        ('new', 'Create a New Request'),
        ('reset', 'Reset Last Request'),
    ], default='new', required=True)
    stage_ids = fields.One2many('absar.approval.stage', 'workflow_id', copy=True)
    stage_count = fields.Integer(compute='_compute_stage_count')
    note = fields.Html()

    approved_action = fields.Selection([
        ('none', 'No Automatic Action'),
        ('method', 'Call a Model Method'),
        ('write', 'Write a Field Value'),
    ], default='none', required=True, help='Action executed on the business record after final approval.')
    approved_method = fields.Char(help='Technical method name, for example action_post or action_create_po.')
    approved_field_id = fields.Many2one(
        'ir.model.fields', string='Approved Field', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', ['selection', 'char', 'boolean', 'integer', 'float'])]",
    )
    approved_value = fields.Char(help='Value written after approval. Boolean values accept true/false.')
    rejected_action = fields.Selection([
        ('none', 'No Automatic Action'),
        ('method', 'Call a Model Method'),
        ('write', 'Write a Field Value'),
    ], default='none', required=True, help='Action executed on the business record after rejection.')
    rejected_method = fields.Char(help='Technical rejection/reset method name.')
    rejected_field_id = fields.Many2one(
        'ir.model.fields', string='Rejected Field', ondelete='set null',
        domain="[('model_id', '=', model_id), ('store', '=', True), ('ttype', 'in', ['selection', 'char', 'boolean', 'integer', 'float'])]",
    )
    rejected_value = fields.Char()

    _sql_constraints = [
        ('workflow_name_company_uniq', 'unique(name, model_id, company_id)',
         'A workflow with this name already exists for the model and company.'),
    ]

    @api.depends('stage_ids')
    def _compute_stage_count(self):
        for rec in self:
            rec.stage_count = len(rec.stage_ids)

    @api.constrains('domain')
    def _check_domain(self):
        for rec in self:
            try:
                domain = safe_eval(rec.domain or '[]', {'uid': self.env.uid, 'user': self.env.user})
                if not isinstance(domain, (list, tuple)):
                    raise ValueError('Domain must be a list or tuple.')
                expression.normalize_domain(domain)
            except Exception as exc:
                raise ValidationError(_('Invalid workflow domain: %s') % exc) from exc

    @api.constrains('stage_ids')
    def _check_stages(self):
        for rec in self:
            if rec.stage_ids and not all(stage.sequence >= 0 for stage in rec.stage_ids):
                raise ValidationError(_('Stage sequence cannot be negative.'))

    @api.constrains('approved_action', 'approved_method', 'approved_field_id',
                    'rejected_action', 'rejected_method', 'rejected_field_id')
    def _check_completion_actions(self):
        for rec in self:
            for action, method, field, label in [
                (rec.approved_action, rec.approved_method, rec.approved_field_id, _('approved')),
                (rec.rejected_action, rec.rejected_method, rec.rejected_field_id, _('rejected')),
            ]:
                if action == 'method' and (not method or not method.isidentifier() or method.startswith('_')):
                    raise ValidationError(_('Enter a valid public method name for the %s action.') % label)
                if action == 'write' and not field:
                    raise ValidationError(_('Select a field for the %s action.') % label)

    def _convert_action_value(self, field, value):
        self.ensure_one()
        if field.ttype == 'boolean':
            return str(value).strip().lower() in ('1', 'true', 'yes', 'on')
        if field.ttype == 'integer':
            return int(value or 0)
        if field.ttype == 'float':
            return float(value or 0.0)
        return value or False

    def execute_target_action(self, record, outcome):
        self.ensure_one()
        action = self.approved_action if outcome == 'approved' else self.rejected_action
        method = self.approved_method if outcome == 'approved' else self.rejected_method
        field = self.approved_field_id if outcome == 'approved' else self.rejected_field_id
        value = self.approved_value if outcome == 'approved' else self.rejected_value
        if action == 'none':
            return True
        if action == 'method':
            if method not in record or method.startswith('_'):
                raise ValidationError(_('Method %s does not exist on %s.') % (method, record._description))
            getattr(record, method)()
            return True
        if action == 'write':
            if field.model != record._name or field.name not in record._fields:
                raise ValidationError(_('Configured field is not valid for this record.'))
            record.write({field.name: self._convert_action_value(field, value)})
        return True

    def matches_record(self, record):
        self.ensure_one()
        if record._name != self.model:
            return False
        if self.company_id and 'company_id' in record._fields and record.company_id != self.company_id:
            return False
        domain = safe_eval(self.domain or '[]', {
            'uid': self.env.uid,
            'user': self.env.user,
            'company': self.env.company,
            'record': record,
            'context': dict(self.env.context),
        })
        return bool(record.filtered_domain(domain))

    @api.model
    def find_workflow(self, record):
        company = record.company_id if 'company_id' in record._fields else self.env.company
        workflows = self.search([
            ('model', '=', record._name),
            ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], order='company_id desc, sequence, id')
        return next((workflow for workflow in workflows if workflow.matches_record(record)), self.browse())


class AbsarApprovalStage(models.Model):
    _name = 'absar.approval.stage'
    _description = 'Approval Stage'
    _order = 'workflow_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    workflow_id = fields.Many2one('absar.approval.workflow', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one(related='workflow_id.model_id', store=True, readonly=True)
    sequence = fields.Integer(default=10, required=True)
    approval_mode = fields.Selection([
        ('any', 'Any One Approver'),
        ('all', 'All Approvers'),
        ('count', 'Minimum Number'),
    ], default='any', required=True)
    minimum_approvals = fields.Integer(default=1)
    approver_source = fields.Selection([
        ('users', 'Specific Users'),
        ('groups', 'Security Groups'),
        ('field', 'Users from Record Field'),
    ], default='users', required=True)
    user_ids = fields.Many2many(
        'res.users', 'absar_stage_user_rel', 'stage_id', 'user_id',
        string='Approvers',
        domain="[('active', '=', True), ('share', '=', False)]",
        help='Select internal Odoo users who may approve this stage.',
    )
    group_ids = fields.Many2many('res.groups', 'absar_stage_group_rel', 'stage_id', 'group_id', string='Approver Groups')
    approver_field_id = fields.Many2one(
        'ir.model.fields', string='Approver Field', ondelete='set null',
        domain="[('model_id', '=', model_id), ('relation', '=', 'res.users'), ('ttype', 'in', ['many2one', 'many2many'])]",
        help='A relational field on the target model whose value contains res.users records.',
    )
    deadline_days = fields.Integer(default=0, help='Calendar days after the stage starts. Zero means no deadline.')
    require_approval_comment = fields.Boolean()
    require_rejection_comment = fields.Boolean(default=True)
    notify_requester = fields.Boolean(default=True)
    can_reject = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    description = fields.Html()

    @api.constrains('minimum_approvals', 'approval_mode')
    def _check_minimum_approvals(self):
        for rec in self:
            if rec.minimum_approvals < 1:
                raise ValidationError(_('Minimum approvals must be at least one.'))

    @api.constrains('approver_source', 'user_ids', 'group_ids', 'approver_field_id')
    def _check_approver_configuration(self):
        for rec in self:
            if rec.approver_source == 'users' and not rec.user_ids:
                raise ValidationError(_('Add at least one user to stage %s.') % rec.name)
            if rec.approver_source == 'groups' and not rec.group_ids:
                raise ValidationError(_('Add at least one group to stage %s.') % rec.name)
            if rec.approver_source == 'field' and not rec.approver_field_id:
                raise ValidationError(_('Select an approver field for stage %s.') % rec.name)

    def resolve_approvers(self, record):
        self.ensure_one()
        users = self.env['res.users']
        if self.approver_source == 'users':
            users = self.user_ids
        elif self.approver_source == 'groups':
            users = self.group_ids.mapped('user_ids')
        elif self.approver_source == 'field':
            value = record[self.approver_field_id.name]
            users = value if value._name == 'res.users' else self.env['res.users']
        return users.filtered(lambda user: user.active and not user.share and self.workflow_id.company_id in user.company_ids if self.workflow_id.company_id else user.active and not user.share)
