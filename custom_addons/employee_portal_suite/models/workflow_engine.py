from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class EmployeePortalApprovalRole(models.Model):
    _name = 'employee.portal.approval.role'
    _description = 'Employee Portal Approval Role'
    _order = 'company_id, sequence, name'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company, index=True
    )
    description = fields.Char()
    default_user_ids = fields.Many2many(
        'res.users', 'eps_approval_role_default_user_rel', 'role_id', 'user_id',
        string='Default Approvers',
        help='Used when the selected project has no project-specific assignment for this role.'
    )
    linked_role_assignment_id = fields.Many2one(
        'employee.portal.role.assignment', string='Linked Existing Role',
        help='Optional. Reuse one of the existing Employee Portal security roles as the default approver source.'
    )
    project_assignment_ids = fields.One2many(
        'employee.portal.project.role.assignment', 'approval_role_id', string='Project Assignments'
    )

    _sql_constraints = [
        ('approval_role_name_company_uniq', 'unique(name, company_id)',
         'Approval Role names must be unique per company.'),
    ]

    def resolve_users(self, request_record):
        self.ensure_one()
        project = getattr(request_record, 'project_id', False)
        if project:
            assignment = self.env['employee.portal.project.role.assignment'].sudo().search([
                ('active', '=', True),
                ('project_id', '=', project.id),
                ('approval_role_id', '=', self.id),
            ], limit=1)
            if assignment:
                return assignment.user_ids

        if self.linked_role_assignment_id:
            group = self.linked_role_assignment_id._group()
            if group:
                return group.sudo().users
        return self.default_user_ids


class EmployeePortalProjectRoleAssignment(models.Model):
    _name = 'employee.portal.project.role.assignment'
    _description = 'Project Approval Role Assignment'
    _order = 'project_id, approval_role_id'

    active = fields.Boolean(default=True)
    project_id = fields.Many2one('project.project', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='project_id.company_id', store=True, readonly=True, index=True)
    approval_role_id = fields.Many2one(
        'employee.portal.approval.role', required=True, ondelete='cascade', index=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]"
    )
    user_ids = fields.Many2many(
        'res.users', 'eps_project_role_user_rel', 'assignment_id', 'user_id',
        string='Approvers', required=True
    )
    note = fields.Char()

    _sql_constraints = [
        ('project_approval_role_uniq', 'unique(project_id, approval_role_id)',
         'A project can only have one assignment for the same Approval Role.'),
    ]

    @api.constrains('project_id', 'approval_role_id')
    def _check_same_company(self):
        for rec in self:
            if rec.project_id.company_id and rec.approval_role_id.company_id != rec.project_id.company_id:
                raise ValidationError(_('The Approval Role and Project must belong to the same company.'))


class EmployeePortalWorkflow(models.Model):
    _name = 'employee.portal.workflow'
    _description = 'Employee Portal Approval Workflow'
    _order = 'applies_to, project_id, sequence, name'

    is_template = fields.Boolean(default=False, copy=False)
    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    applies_to = fields.Selection([
        ('employee_request', 'Employee Request'),
        ('material_request', 'Material Request'),
    ], required=True, default='employee_request')
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        domain="[('company_id', '=', company_id)]",
        help='Leave empty to use this workflow as a company/default workflow.'
    )
    employee_request_type = fields.Selection([
        ('leave', 'Leave Request'),
        ('housing', 'Housing Allowance'),
        ('advance', 'Salary Advance'),
        ('travel', 'Business Trip / Travel Request'),
        ('training', 'Training Request'),
        ('medical', 'Medical Reimbursement'),
        ('vacation_settlement', 'Vacation Settlement'),
        ('asset', 'Asset / Equipment Request'),
        ('letter', 'Letter Request'),
        ('bank', 'Change of Bank Account'),
        ('transfer', 'Change of Position / Transfer Request'),
        ('exit', 'End of Service / Clearance'),
        ('other', 'Other'),
    ], string='Employee Request Type',
       help='Optional. Leave empty to apply to all Employee Request types for the selected project/default scope.')
    step_ids = fields.One2many(
        'employee.portal.workflow.step', 'workflow_id', string='Approval Steps', copy=True
    )
    step_count = fields.Integer(compute='_compute_step_count')

    @api.depends('step_ids')
    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.step_ids)

    def action_use_template(self):
        self.ensure_one()
        if not self.is_template:
            raise UserError(_('Choose a workflow template first.'))
        workflow = self.copy({'name': self.name + _(' - Project Copy'),
                              'is_template': False, 'active': False, 'project_id': False})
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': workflow.id, 'view_mode': 'form', 'target': 'current',
                'context': {'active_test': False}}

    @api.constrains('is_template', 'active')
    def _check_template_inactive(self):
        if any(rec.is_template and rec.active for rec in self):
            raise ValidationError(_('Templates cannot be activated. Use Create Project Workflow, fill the project and approvers, then activate the copy.'))

    @api.onchange('applies_to')
    def _onchange_applies_to(self):
        if self.applies_to != 'employee_request':
            self.employee_request_type = False

    @api.constrains('applies_to', 'employee_request_type')
    def _check_request_type_scope(self):
        for rec in self:
            if rec.applies_to != 'employee_request' and rec.employee_request_type:
                raise ValidationError(_('Employee Request Type can only be used on Employee Request workflows.'))

    @api.constrains('company_id', 'project_id')
    def _check_project_company(self):
        for rec in self:
            if rec.project_id and rec.project_id.company_id and rec.project_id.company_id != rec.company_id:
                raise ValidationError(_('The workflow company must match the selected project company.'))

    @api.constrains('active', 'company_id', 'applies_to', 'project_id', 'employee_request_type')
    def _check_duplicate_scope(self):
        for rec in self.filtered('active'):
            domain = [
                ('id', '!=', rec.id),
                ('active', '=', True),
                ('company_id', '=', rec.company_id.id),
                ('applies_to', '=', rec.applies_to),
                ('project_id', '=', rec.project_id.id if rec.project_id else False),
            ]
            if rec.applies_to == 'employee_request':
                domain.append(('employee_request_type', '=', rec.employee_request_type or False))
            else:
                domain.append(('employee_request_type', '=', False))
            if self.search_count(domain):
                scope = rec.project_id.display_name if rec.project_id else _('Default')
                raise ValidationError(_(
                    'Only one active workflow can exist for the same request type and scope. '
                    'Duplicate scope: %s.'
                ) % scope)

    @api.model
    def resolve_workflow(self, applies_to, project=False, employee_request_type=False, company=False):
        """Resolve the most specific active workflow.

        Priority for ER: project+type, project+all types, default+type, default+all.
        Priority for MR: project, then default.
        """
        company = company or (project.company_id if project else self.env.company)
        base = [('is_template', '=', False), ('active', '=', True), ('company_id', '=', company.id), ('applies_to', '=', applies_to)]
        project_id = project.id if project else False
        candidates = []
        if applies_to == 'employee_request':
            if project_id and employee_request_type:
                candidates.append(base + [('project_id', '=', project_id), ('employee_request_type', '=', employee_request_type)])
            if project_id:
                candidates.append(base + [('project_id', '=', project_id), ('employee_request_type', '=', False)])
            if employee_request_type:
                candidates.append(base + [('project_id', '=', False), ('employee_request_type', '=', employee_request_type)])
            candidates.append(base + [('project_id', '=', False), ('employee_request_type', '=', False)])
        else:
            if project_id:
                candidates.append(base + [('project_id', '=', project_id), ('employee_request_type', '=', False)])
            candidates.append(base + [('project_id', '=', False), ('employee_request_type', '=', False)])

        for domain in candidates:
            workflow = self.search(domain, order='sequence, id', limit=1)
            if workflow:
                return workflow
        return self.browse()


class EmployeePortalWorkflowStep(models.Model):
    _name = 'employee.portal.workflow.step'
    _description = 'Employee Portal Workflow Step'
    _order = 'sequence, id'

    workflow_id = fields.Many2one(
        'employee.portal.workflow', required=True, ondelete='cascade', index=True
    )
    sequence = fields.Integer(default=10, required=True)
    name = fields.Char(string='Step Name', required=True)
    approver_type = fields.Selection([
        ('approval_role', 'Approval Role'),
        ('role', 'Legacy Security Role'),
        ('user', 'Specific User'),
        ('employee_manager', "Employee's Manager"),
        ('project_manager', 'Project Manager'),
        ('store_manager', 'Store Manager'),
    ], required=True, default='approval_role')
    approval_role_id = fields.Many2one(
        'employee.portal.approval.role', string='Approval Role',
        help='Recommended. A configurable business approval role whose user can vary by project.'
    )
    role_assignment_id = fields.Many2one(
        'employee.portal.role.assignment',
        string='Approver Role',
        help='All users currently assigned to this Employee Portal role will be eligible when the request is submitted.'
    )
    user_id = fields.Many2one('res.users', string='Specific Approver')
    description = fields.Char(string='Instruction / Description')

    @api.onchange('approver_type')
    def _onchange_approver_type(self):
        if self.approver_type != 'approval_role':
            self.approval_role_id = False
        if self.approver_type != 'role':
            self.role_assignment_id = False
        if self.approver_type != 'user':
            self.user_id = False

    @api.constrains('approver_type', 'approval_role_id', 'role_assignment_id', 'user_id')
    def _check_approver_source(self):
        for rec in self:
            if rec.approver_type == 'approval_role' and not rec.approval_role_id:
                raise ValidationError(_('Select an Approval Role for step "%s".') % rec.name)
            if rec.approver_type == 'role' and not rec.role_assignment_id:
                raise ValidationError(_('Select a Legacy Security Role for step "%s".') % rec.name)
            if rec.approver_type == 'user' and not rec.user_id:
                raise ValidationError(_('Select a Specific Approver for step "%s".') % rec.name)

    def resolve_users(self, request_record):
        self.ensure_one()
        if self.approver_type == 'approval_role':
            return self.approval_role_id.sudo().resolve_users(request_record) if self.approval_role_id else self.env['res.users']
        if self.approver_type == 'role':
            group = self.role_assignment_id._group() if self.role_assignment_id else False
            return group.sudo().users if group else self.env['res.users']
        if self.approver_type == 'user':
            return self.user_id
        if self.approver_type == 'employee_manager':
            manager = request_record.employee_id.parent_id if request_record.employee_id else False
            return manager.user_id if manager else self.env['res.users']
        if self.approver_type == 'project_manager':
            project = getattr(request_record, 'project_id', False)
            return project.project_manager_user_id if project else self.env['res.users']
        if self.approver_type == 'store_manager':
            project = getattr(request_record, 'project_id', False)
            return project.store_manager_user_id if project else self.env['res.users']
        return self.env['res.users']


class EmployeePortalWorkflowApprovalLine(models.Model):
    _name = 'employee.portal.workflow.approval.line'
    _description = 'Employee Portal Workflow Approval Line'
    _order = 'sequence, id'

    employee_request_id = fields.Many2one('employee.request', ondelete='cascade', index=True)
    material_request_id = fields.Many2one('material.request', ondelete='cascade', index=True)
    workflow_id = fields.Many2one('employee.portal.workflow', readonly=True, index=True)
    source_step_id = fields.Many2one('employee.portal.workflow.step', readonly=True, ondelete='set null')
    sequence = fields.Integer(required=True, readonly=True)
    name = fields.Char(string='Approval Step', required=True, readonly=True)
    approver_type = fields.Selection([
        ('approval_role', 'Approval Role'),
        ('role', 'Legacy Security Role'),
        ('user', 'Specific User'),
        ('employee_manager', "Employee's Manager"),
        ('project_manager', 'Project Manager'),
        ('store_manager', 'Store Manager'),
    ], readonly=True)
    role_name = fields.Char(readonly=True)
    approver_user_ids = fields.Many2many(
        'res.users', 'eps_workflow_approval_user_rel', 'approval_line_id', 'user_id',
        string='Eligible Approvers', readonly=True
    )
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='waiting', required=True, readonly=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_date = fields.Datetime(readonly=True)
    rejected_by = fields.Many2one('res.users', readonly=True)
    rejected_date = fields.Datetime(readonly=True)
    comment = fields.Text()

    @api.constrains('employee_request_id', 'material_request_id')
    def _check_parent(self):
        for rec in self:
            if bool(rec.employee_request_id) == bool(rec.material_request_id):
                raise ValidationError(_('A workflow approval line must belong to exactly one request.'))

    def _request(self):
        self.ensure_one()
        return self.employee_request_id or self.material_request_id

    def can_user_approve(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if user.has_group('employee_portal_suite.group_employee_portal_superadmin'):
            return self.state == 'pending'
        return self.state == 'pending' and user in self.approver_user_ids
