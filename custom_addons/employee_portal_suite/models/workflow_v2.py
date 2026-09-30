from datetime import timedelta

from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval


class EmployeePortalWorkflow(models.Model):
    _inherit = 'employee.portal.workflow'

    active = fields.Boolean(default=False)

    validation_state = fields.Selection([
        ('not_validated', 'Not Validated'),
        ('valid', 'Valid'),
        ('warning', 'Valid with Warnings'),
    ], default='not_validated', readonly=True, copy=False)
    validation_message = fields.Text(readonly=True, copy=False)
    validated_on = fields.Datetime(readonly=True, copy=False)
    validated_by = fields.Many2one('res.users', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            if vals.get('active'):
                errors, _warnings = rec._validation_lines()
                if errors:
                    raise ValidationError('\n'.join(errors))
        return records

    def write(self, vals):
        activating = bool(vals.get('active'))
        result = super().write(vals)
        if activating:
            for rec in self:
                errors, _warnings = rec._validation_lines()
                if errors:
                    raise ValidationError('\n'.join(errors))
        return result

    def _validation_lines(self, request_record=None):
        self.ensure_one()
        errors = []
        warnings = []
        steps = self.step_ids.sorted(lambda s: (s.sequence, s.id))
        if not steps:
            errors.append(_('The workflow has no approval steps.'))
        sequences = [step.sequence for step in steps]
        duplicates = sorted({x for x in sequences if sequences.count(x) > 1})
        if duplicates:
            errors.append(_('Duplicate step sequences: %s') % ', '.join(map(str, duplicates)))

        for step in steps:
            try:
                step._validate_configuration()
            except ValidationError as exc:
                errors.append(str(exc))
            if request_record:
                try:
                    if not step.applies_to_record(request_record):
                        continue
                    users = step.sudo().resolve_users(request_record)
                    if not users:
                        errors.append(_('Step "%s" does not resolve to any approver.') % step.name)
                except Exception as exc:
                    errors.append(_('Step "%s": %s') % (step.name, str(exc)))
            elif step.approver_type in ('employee_manager', 'project_manager', 'store_manager'):
                warnings.append(_('Step "%s" uses a runtime approver and should be tested with a sample request.') % step.name)

        return errors, warnings

    def action_validate_workflow(self):
        for rec in self:
            errors, warnings = rec._validation_lines()
            if errors:
                raise ValidationError('\n'.join(errors))
            message = '\n'.join(warnings) if warnings else _('Workflow configuration is valid.')
            rec.write({
                'validation_state': 'warning' if warnings else 'valid',
                'validation_message': message,
                'validated_on': fields.Datetime.now(),
                'validated_by': self.env.user.id,
            })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Workflow Validation'),
                'message': _('Workflow configuration is valid.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_open_test_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Test Workflow'),
            'res_model': 'employee.portal.workflow.test.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_workflow_id': self.id,
                'default_project_id': self.project_id.id,
                'default_request_type': self.employee_request_type,
            },
        }


class EmployeePortalWorkflowStep(models.Model):
    _inherit = 'employee.portal.workflow.step'

    condition_domain = fields.Char(
        string='Condition Domain',
        default='[]',
        help="Optional Odoo domain evaluated on the request. Example: [('request_type','=','leave')]. Leave [] to always run this step."
    )
    sla_hours = fields.Float(
        string='Approval SLA (Hours)', default=24.0,
        help='Expected approval time after this step becomes pending. Set 0 to disable overdue tracking.'
    )

    def _condition_domain_value(self):
        self.ensure_one()
        text = (self.condition_domain or '[]').strip() or '[]'
        try:
            domain = safe_eval(text, {'uid': self.env.uid})
        except Exception as exc:
            raise ValidationError(_('Invalid condition domain on step "%s": %s') % (self.name, exc))
        if not isinstance(domain, (list, tuple)):
            raise ValidationError(_('Condition Domain on step "%s" must be an Odoo domain list.') % self.name)
        return list(domain)

    def applies_to_record(self, request_record):
        self.ensure_one()
        domain = self._condition_domain_value()
        if not domain:
            return True
        try:
            return bool(request_record.filtered_domain(domain))
        except Exception as exc:
            raise ValidationError(_('Condition on step "%s" cannot be evaluated: %s') % (self.name, exc))

    def _validate_configuration(self):
        self.ensure_one()
        self._condition_domain_value()
        if self.approver_type == 'approval_role' and not self.approval_role_id:
            raise ValidationError(_('Step "%s" requires an Approval Role.') % self.name)
        if self.approver_type == 'role' and not self.role_assignment_id:
            raise ValidationError(_('Step "%s" requires a Legacy Security Role.') % self.name)
        if self.approver_type == 'user' and not self.user_id:
            raise ValidationError(_('Step "%s" requires a Specific Approver.') % self.name)
        if self.sla_hours < 0:
            raise ValidationError(_('Approval SLA cannot be negative on step "%s".') % self.name)
        return True

    @api.constrains('condition_domain', 'sla_hours')
    def _check_v2_configuration(self):
        for rec in self:
            rec._validate_configuration()


class EmployeePortalApprovalDelegation(models.Model):
    _name = 'employee.portal.approval.delegation'
    _description = 'Approval Delegation'
    _order = 'date_from desc, id desc'

    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    user_id = fields.Many2one('res.users', string='Original Approver', required=True, index=True)
    delegate_user_id = fields.Many2one('res.users', string='Delegate To', required=True, index=True)
    approval_role_id = fields.Many2one(
        'employee.portal.approval.role', string='Approval Role',
        help='Optional. Leave empty to delegate all workflow approvals for this user during the period.'
    )
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date(required=True)
    note = fields.Char()

    @api.constrains('user_id', 'delegate_user_id', 'date_from', 'date_to')
    def _check_delegation(self):
        for rec in self:
            if rec.user_id == rec.delegate_user_id:
                raise ValidationError(_('An approver cannot delegate to themselves.'))
            if rec.date_to < rec.date_from:
                raise ValidationError(_('Delegation end date cannot be before the start date.'))

    @api.model
    def delegates_for(self, original_users, approval_role=False, date=None):
        if not original_users:
            return self.env['res.users']
        date = date or fields.Date.context_today(self)
        domain = [
            ('active', '=', True),
            ('user_id', 'in', original_users.ids),
            ('date_from', '<=', date),
            ('date_to', '>=', date),
            ('company_id', '=', self.env.company.id),
        ]
        delegations = self.sudo().search(domain)
        if approval_role:
            delegations = delegations.filtered(lambda d: not d.approval_role_id or d.approval_role_id == approval_role)
        else:
            delegations = delegations.filtered(lambda d: not d.approval_role_id)
        return delegations.mapped('delegate_user_id')


class EmployeePortalWorkflowApprovalLine(models.Model):
    _inherit = 'employee.portal.workflow.approval.line'

    state = fields.Selection(selection_add=[
        ('returned', 'Returned for Correction'),
        ('skipped', 'Skipped'),
    ], ondelete={'returned': 'set default', 'skipped': 'set default'})
    approval_role_id = fields.Many2one('employee.portal.approval.role', readonly=True, index=True)
    pending_date = fields.Datetime(readonly=True)
    due_date = fields.Datetime(readonly=True)
    is_overdue = fields.Boolean(readonly=True, default=False, index=True)
    duration_hours = fields.Float(compute='_compute_workflow_metrics', store=True, group_operator='avg')
    returned_by = fields.Many2one('res.users', readonly=True)
    returned_date = fields.Datetime(readonly=True)
    return_reason = fields.Text(readonly=True)
    return_count = fields.Integer(default=0, readonly=True)
    override_by = fields.Many2one('res.users', readonly=True)
    override_date = fields.Datetime(readonly=True)
    override_reason = fields.Text(readonly=True)
    delegated_from_user_id = fields.Many2one('res.users', readonly=True)
    project_id = fields.Many2one('project.project', compute='_compute_report_fields', store=True, index=True)
    company_id = fields.Many2one('res.company', compute='_compute_report_fields', store=True, index=True)
    request_name = fields.Char(compute='_compute_report_fields', store=True, index=True)
    request_model_label = fields.Selection([
        ('employee_request', 'Employee Request'),
        ('material_request', 'Material Request'),
    ], compute='_compute_report_fields', store=True, index=True)

    @api.depends('employee_request_id', 'employee_request_id.project_id', 'employee_request_id.name',
                 'material_request_id', 'material_request_id.project_id', 'material_request_id.name')
    def _compute_report_fields(self):
        for line in self:
            request = line.employee_request_id or line.material_request_id
            line.project_id = request.project_id if request else False
            line.company_id = (request.project_id.company_id if request and request.project_id else (request.employee_id.company_id if request else False))
            line.request_name = request.name if request else False
            line.request_model_label = 'employee_request' if line.employee_request_id else ('material_request' if line.material_request_id else False)

    @api.depends('pending_date', 'approved_date', 'rejected_date', 'returned_date', 'state')
    def _compute_workflow_metrics(self):
        now = fields.Datetime.now()
        for line in self:
            end = line.approved_date or line.rejected_date or line.returned_date or (now if line.pending_date else False)
            if line.pending_date and end:
                line.duration_hours = max(0.0, (end - line.pending_date).total_seconds() / 3600.0)
            else:
                line.duration_hours = 0.0

    @api.model
    def _cron_update_overdue(self):
        now = fields.Datetime.now()
        pending = self.sudo().search([('state', '=', 'pending')])
        overdue = pending.filtered(lambda line: line.due_date and line.due_date < now)
        current = pending - overdue
        if overdue:
            overdue.write({'is_overdue': True})
        if current:
            current.write({'is_overdue': False})
        stale = self.sudo().search([('state', '!=', 'pending'), ('is_overdue', '=', True)])
        if stale:
            stale.write({'is_overdue': False})
        return True

    def _effective_users(self):
        self.ensure_one()
        delegates = self.env['employee.portal.approval.delegation'].sudo().delegates_for(
            self.approver_user_ids,
            approval_role=self.approval_role_id,
        )
        return self.approver_user_ids | delegates

    def is_user_direct_approver(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return self.state == 'pending' and user in self._effective_users()

    def delegated_from_for(self, user):
        self.ensure_one()
        if user in self.approver_user_ids:
            return self.env['res.users']
        date = fields.Date.context_today(self)
        delegations = self.env['employee.portal.approval.delegation'].sudo().search([
            ('active', '=', True),
            ('user_id', 'in', self.approver_user_ids.ids),
            ('delegate_user_id', '=', user.id),
            ('date_from', '<=', date),
            ('date_to', '>=', date),
            ('company_id', '=', self.company_id.id or self.env.company.id),
        ])
        if self.approval_role_id:
            delegations = delegations.filtered(lambda d: not d.approval_role_id or d.approval_role_id == self.approval_role_id)
        else:
            delegations = delegations.filtered(lambda d: not d.approval_role_id)
        return delegations[:1].user_id

    def can_user_approve(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if self.state != 'pending':
            return False
        if user.has_group('employee_portal_suite.group_employee_portal_superadmin'):
            return True
        return user in self._effective_users()

    def user_has_approval_involvement(self, user=None):
        """Whether *user* legitimately belongs to this approval line.

        This is intentionally broader than ``can_user_approve``: it keeps the
        approval area available after the user has approved/rejected/returned
        a step, and it includes an active delegate while the delegated step is
        pending.  It does not grant unrelated employees access.
        """
        self.ensure_one()
        user = user or self.env.user
        if user.has_group('employee_portal_suite.group_employee_portal_superadmin'):
            return True
        if user in self.approver_user_ids:
            return True
        if user in (self.approved_by | self.rejected_by | self.returned_by | self.override_by):
            return True
        return bool(self.state == 'pending' and user in self._effective_users())

    @api.model
    def user_has_approval_area_access(self, user, request_kind):
        """Return True when the user should see the ER/MR approval area.

        ``request_kind`` is ``employee_request`` or ``material_request``.
        Legacy group access is handled by callers; this method covers dynamic
        workflow assignments, history, and active delegation.
        """
        field_name = {
            'employee_request': 'employee_request_id',
            'material_request': 'material_request_id',
        }.get(request_kind)
        if not field_name:
            return False
        lines = self.sudo().search([(field_name, '!=', False)])
        return any(line.user_has_approval_involvement(user) for line in lines)

    @api.model
    def request_ids_for_user(self, user, request_kind):
        """Dynamic workflow request ids visible to a user through involvement."""
        field_name = {
            'employee_request': 'employee_request_id',
            'material_request': 'material_request_id',
        }.get(request_kind)
        if not field_name:
            return []
        lines = self.sudo().search([(field_name, '!=', False)])
        visible = lines.filtered(lambda line: line.user_has_approval_involvement(user))
        return visible.mapped(field_name).ids


    @api.model
    def retrieve_workflow_dashboard(self):
        """Compact KPI payload used by the backend Workflow Reports dashboard."""
        today = fields.Date.context_today(self)
        counts = {
            'all_count': self.search_count([]),
            'pending_count': self.search_count([('state', '=', 'pending')]),
            'waiting_count': self.search_count([('state', '=', 'waiting')]),
            'overdue_count': self.search_count([('state', '=', 'pending'), ('is_overdue', '=', True)]),
            'approved_count': self.search_count([('state', '=', 'approved')]),
            'returned_count': self.search_count([('state', '=', 'returned')]),
            'rejected_count': self.search_count([('state', '=', 'rejected')]),
            'skipped_count': self.search_count([('state', '=', 'skipped')]),
            'override_count': self.search_count([('override_by', '!=', False)]),
        }
        grouped = self.read_group(
            [('duration_hours', '>', 0.0), ('state', 'in', ['approved', 'rejected', 'returned'])],
            ['duration_hours:avg'], [],
        )
        avg_hours = grouped[0].get('duration_hours', 0.0) if grouped else 0.0
        counts.update({
            'avg_hours': round(avg_hours or 0.0, 1),
            'active_workflow_count': self.env['employee.portal.workflow'].search_count([('active', '=', True)]),
            'approval_role_count': self.env['employee.portal.approval.role'].search_count([('active', '=', True)]),
            'active_delegation_count': self.env['employee.portal.approval.delegation'].search_count([
                ('active', '=', True), ('date_from', '<=', today), ('date_to', '>=', today),
            ]),
        })
        return counts


class EmployeePortalWorkflowTestWizard(models.TransientModel):
    _name = 'employee.portal.workflow.test.wizard'
    _description = 'Test Employee Portal Workflow'

    workflow_id = fields.Many2one('employee.portal.workflow', required=True, readonly=True)
    applies_to = fields.Selection(related='workflow_id.applies_to', readonly=True)
    project_id = fields.Many2one('project.project')
    employee_id = fields.Many2one('hr.employee', required=True)
    request_type = fields.Selection(selection=lambda self: self.env['employee.request']._fields['request_type'].selection)
    result = fields.Text(readonly=True)

    def action_test(self):
        self.ensure_one()
        workflow = self.workflow_id
        if workflow.applies_to == 'employee_request':
            request = self.env['employee.request'].new({
                'employee_id': self.employee_id.id,
                'project_id': self.project_id.id,
                'request_type': self.request_type or workflow.employee_request_type or 'other',
            })
        else:
            request = self.env['material.request'].new({
                'employee_id': self.employee_id.id,
                'project_id': self.project_id.id,
            })
        errors, warnings = workflow._validation_lines(request)
        lines = []
        for index, step in enumerate(workflow.step_ids.sorted(lambda s: (s.sequence, s.id)), 1):
            if not step.applies_to_record(request):
                lines.append('%s. %s -> SKIPPED (condition not matched)' % (index, step.name))
                continue
            users = step.sudo().resolve_users(request)
            names = ', '.join(users.mapped('name')) if users else 'NO APPROVER'
            lines.append('%s. %s -> %s' % (index, step.name, names))
        if warnings:
            lines.append('\nWarnings:\n- ' + '\n- '.join(warnings))
        if errors:
            lines.append('\nErrors:\n- ' + '\n- '.join(errors))
        self.result = '\n'.join(lines)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class EmployeePortalWorkflowReturnWizard(models.TransientModel):
    _name = 'employee.portal.workflow.return.wizard'
    _description = 'Return Workflow Request for Correction'

    reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        model = self.env.context.get('active_model')
        record_id = self.env.context.get('active_id')
        if model not in ('employee.request', 'material.request') or not record_id:
            raise UserError(_('No workflow request was selected.'))
        record = self.env[model].browse(record_id).exists()
        record._workflow_return_confirm(self.reason)
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class EmployeePortalWorkflowOverrideWizard(models.TransientModel):
    _name = 'employee.portal.workflow.override.wizard'
    _description = 'Super Admin Workflow Override'

    reason = fields.Text(required=True, string='Override Reason')

    def action_confirm(self):
        self.ensure_one()
        model = self.env.context.get('active_model')
        record_id = self.env.context.get('active_id')
        if model not in ('employee.request', 'material.request') or not record_id:
            raise UserError(_('No workflow request was selected.'))
        record = self.env[model].browse(record_id).exists()
        record.with_context(workflow_override_reason=self.reason, workflow_override_confirmed=True).action_workflow_approve()
        return {'type': 'ir.actions.client', 'tag': 'reload'}


class ProjectProject(models.Model):
    _inherit = 'project.project'

    employee_portal_workflow_ids = fields.One2many(
        'employee.portal.workflow', 'project_id', string='Employee Portal Workflows'
    )




class WorkflowRequestMixin(models.AbstractModel):
    _name = 'employee.portal.workflow.request.mixin'
    _description = 'Employee Portal Workflow Request Helpers'

    workflow_progress_html = fields.Html(compute='_compute_workflow_progress_html', sanitize=False)

    def _workflow_notify_line(self, line):
        self.ensure_one()
        users = line.sudo()._effective_users()
        for user in users:
            self._notify_user(
                user,
                _('%s requires your approval') % self.name,
                _('Approval step "%s" is waiting for your action.') % line.name,
            )
            self._schedule_activity(
                user,
                _('Workflow Approval Needed'),
                _('Please review %s - %s.') % (self.name, line.name),
            )

    def _compute_workflow_progress_html(self):
        labels = {
            'approved': ('✓', 'text-success'),
            'pending': ('●', 'text-primary'),
            'waiting': ('○', 'text-muted'),
            'rejected': ('✕', 'text-danger'),
            'returned': ('↩', 'text-warning'),
            'skipped': ('—', 'text-muted'),
        }
        for rec in self:
            if not rec.workflow_id or not rec.approval_line_ids:
                rec.workflow_progress_html = False
                continue
            chunks = []
            for line in rec.approval_line_ids.sorted(lambda l: (l.sequence, l.id)):
                icon, css = labels.get(line.state, ('○', 'text-muted'))
                meta = ''
                if line.approved_by:
                    meta = ' · %s' % line.approved_by.name
                elif line.state == 'pending' and line.approver_user_ids:
                    meta = ' · %s' % ', '.join(line._effective_users().mapped('name'))
                if line.is_overdue:
                    meta += ' · OVERDUE'
                chunks.append(
                    '<span class="me-3 %s"><strong>%s %s</strong>%s</span>' % (
                        css, icon, escape(line.name or ''), escape(meta)
                    )
                )
            rec.workflow_progress_html = Markup('<div class="d-flex flex-wrap align-items-center gap-2">%s</div>' % ''.join(chunks))

    def _workflow_line_values(self, workflow):
        self.ensure_one()
        steps = workflow.sudo().step_ids.sorted(lambda step: (step.sequence, step.id))
        if not steps:
            raise UserError(_('The selected workflow has no approval steps.'))
        values = []
        eligible_index = 0
        prepared = []
        for step in steps:
            applies = step.sudo().applies_to_record(self)
            users = step.sudo().resolve_users(self) if applies else self.env['res.users']
            if applies and not users:
                raise UserError(_('Workflow step "%s" has no approver.') % step.name)
            prepared.append((step, applies, users))
        first_eligible = next((idx for idx, item in enumerate(prepared) if item[1]), None)
        if first_eligible is None:
            raise UserError(_('All workflow steps were skipped by conditions. At least one step must apply.'))
        now = fields.Datetime.now()
        for idx, (step, applies, users) in enumerate(prepared):
            state = 'skipped' if not applies else ('pending' if idx == first_eligible else 'waiting')
            pending_date = now if state == 'pending' else False
            due_date = now + timedelta(hours=step.sla_hours) if state == 'pending' and step.sla_hours else False
            vals = {
                'workflow_id': workflow.id,
                'source_step_id': step.id,
                'sequence': step.sequence,
                'name': step.name,
                'approver_type': step.approver_type,
                'approval_role_id': step.approval_role_id.id,
                'role_name': (step.approval_role_id.name if step.approval_role_id else (step.role_assignment_id.name if step.role_assignment_id else False)),
                'approver_user_ids': [(6, 0, users.ids)],
                'state': state,
                'pending_date': pending_date,
                'due_date': due_date,
            }
            values.append(vals)
        return values

    def _workflow_activate_next(self, approved_line):
        self.ensure_one()
        next_line = self.approval_line_ids.sudo().filtered(lambda l: l.state == 'waiting').sorted(lambda l: (l.sequence, l.id))[:1]
        if not next_line:
            return False
        now = fields.Datetime.now()
        sla = next_line.source_step_id.sla_hours if next_line.source_step_id else 0.0
        next_line.write({
            'state': 'pending',
            'pending_date': now,
            'due_date': now + timedelta(hours=sla) if sla else False,
        })
        self.message_post(body=_('Workflow step approved: %s. Next step: %s.') % (approved_line.name, next_line.name))
        self._workflow_notify_line(next_line)
        return True

    def action_workflow_return(self):
        self.ensure_one()
        line = self.current_approval_line_id.sudo()
        actor = self.env['res.users'].browse(self.env.context.get('workflow_actor_user_id')) or self.env.user
        if self.state != 'workflow' or not line or not line.can_user_approve(actor):
            raise UserError(_('You are not allowed to return this workflow request.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return for Correction'),
            'res_model': 'employee.portal.workflow.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_model': self._name, 'active_id': self.id},
        }

    def _workflow_return_confirm(self, reason):
        self.ensure_one()
        line = self.current_approval_line_id.sudo()
        actor = self.env['res.users'].browse(self.env.context.get('workflow_actor_user_id')) or self.env.user
        if self.state != 'workflow' or not line or not line.can_user_approve(actor):
            raise UserError(_('You are not allowed to return this workflow request.'))
        line.write({
            'state': 'returned',
            'returned_by': actor.id,
            'returned_date': fields.Datetime.now(),
            'return_reason': reason,
            'return_count': line.return_count + 1,
        })
        self.sudo().write({'state': 'returned'})
        self.message_post(body=_('Returned for correction at step "%s" by %s. Reason: %s') % (line.name, actor.name, reason))
        if self.employee_id.user_id:
            self._notify_user(self.employee_id.user_id, _('Request returned for correction'), reason)
        return True

    def action_workflow_resubmit(self):
        for rec in self:
            if rec.state != 'returned' or not rec.workflow_id:
                raise UserError(_('Only a returned configurable-workflow request can be resubmitted.'))
            line = rec.approval_line_ids.sudo().filtered(lambda l: l.state == 'returned').sorted(lambda l: (l.sequence, l.id))[:1]
            if not line:
                raise UserError(_('No returned workflow step was found.'))
            now = fields.Datetime.now()
            sla = line.source_step_id.sla_hours if line.source_step_id else 0.0
            line.write({
                'state': 'pending',
                'pending_date': now,
                'due_date': now + timedelta(hours=sla) if sla else False,
            })
            rec.sudo().write({'state': 'workflow'})
            rec.message_post(body=_('Request corrected and resubmitted to workflow step: %s') % line.name)
            rec._workflow_notify_line(line)
        return True

    def _workflow_prepare_override(self, line, actor):
        direct = line.is_user_direct_approver(actor)
        if actor.has_group('employee_portal_suite.group_employee_portal_superadmin') and not direct:
            reason = self.env.context.get('workflow_override_reason')
            if not reason or not self.env.context.get('workflow_override_confirmed'):
                return {
                    'type': 'ir.actions.act_window',
                    'name': _('Super Admin Override'),
                    'res_model': 'employee.portal.workflow.override.wizard',
                    'view_mode': 'form',
                    'target': 'new',
                    'context': {'active_model': self._name, 'active_id': self.id},
                }
            line.write({
                'override_by': actor.id,
                'override_date': fields.Datetime.now(),
                'override_reason': reason,
            })
            self.message_post(body=_('SUPER ADMIN OVERRIDE at step "%s" by %s. Reason: %s') % (line.name, actor.name, reason))
        return False


class EmployeeRequestWorkflowV2(models.Model):
    _inherit = ['employee.request', 'employee.portal.workflow.request.mixin']
    _name = 'employee.request'

    state = fields.Selection(selection_add=[('returned', 'Returned for Correction')], ondelete={'returned': 'set default'})

    def _notify_workflow_line(self, line):
        return self._workflow_notify_line(line)

    def _start_custom_workflow(self, workflow):
        self.ensure_one()
        workflow.action_validate_workflow()
        values = self._workflow_line_values(workflow)
        for vals in values:
            vals['employee_request_id'] = self.id
        self.sudo().approval_line_ids.unlink()
        lines = self.env['employee.portal.workflow.approval.line'].sudo().create(values)
        self.sudo().write({'workflow_id': workflow.id, 'state': 'workflow'})
        self.message_post(body=_('Request submitted using workflow: %s') % workflow.display_name)
        self._close_activities()
        pending = lines.filtered(lambda l: l.state == 'pending')[:1]
        self._workflow_notify_line(pending)

    def action_workflow_approve(self):
        for rec in self:
            if rec.state != 'workflow':
                raise UserError(_('This request is not in configurable workflow approval.'))
            line = rec.current_approval_line_id.sudo()
            if not line:
                raise UserError(_('No pending workflow step was found.'))
            actor = self.env['res.users'].browse(self.env.context.get('workflow_actor_user_id')) or self.env.user
            if not line.can_user_approve(actor):
                raise UserError(_('You are not an eligible approver for the current workflow step.'))
            override_action = rec._workflow_prepare_override(line, actor)
            if override_action:
                return override_action
            delegated_from = line.delegated_from_for(actor)
            line.write({
                'state': 'approved',
                'approved_by': actor.id,
                'approved_date': fields.Datetime.now(),
                'delegated_from_user_id': delegated_from.id if delegated_from else False,
            })
            rec._close_activities()
            if not rec._workflow_activate_next(line):
                rec._finish_custom_workflow()
        return True

    def action_submit(self):
        returned = self.filtered(lambda r: r.state == 'returned' and r.workflow_id)
        if returned:
            returned.action_workflow_resubmit()
        drafts = self - returned
        return super(EmployeeRequestWorkflowV2, drafts).action_submit() if drafts else True


class MaterialRequestWorkflowV2(models.Model):
    _inherit = ['material.request', 'employee.portal.workflow.request.mixin']
    _name = 'material.request'

    state = fields.Selection(selection_add=[('returned', 'Returned for Correction')], ondelete={'returned': 'set default'})

    def _notify_workflow_line(self, line):
        return self._workflow_notify_line(line)

    def _start_custom_workflow(self, workflow):
        self.ensure_one()
        workflow.action_validate_workflow()
        values = self._workflow_line_values(workflow)
        for vals in values:
            vals['material_request_id'] = self.id
        self.sudo().approval_line_ids.unlink()
        lines = self.env['employee.portal.workflow.approval.line'].sudo().create(values)
        self.sudo().write({'workflow_id': workflow.id, 'state': 'workflow'})
        self.message_post(body=_('Material Request submitted using workflow: %s') % workflow.display_name)
        self.activity_ids.action_done()
        pending = lines.filtered(lambda l: l.state == 'pending')[:1]
        self._workflow_notify_line(pending)

    def action_workflow_approve(self):
        for rec in self:
            if rec.state != 'workflow':
                raise UserError(_('This Material Request is not in configurable workflow approval.'))
            line = rec.current_approval_line_id.sudo()
            if not line:
                raise UserError(_('No pending workflow step was found.'))
            actor = self.env['res.users'].browse(self.env.context.get('workflow_actor_user_id')) or self.env.user
            if not line.can_user_approve(actor):
                raise UserError(_('You are not an eligible approver for the current workflow step.'))
            override_action = rec._workflow_prepare_override(line, actor)
            if override_action:
                return override_action
            delegated_from = line.delegated_from_for(actor)
            line.write({
                'state': 'approved',
                'approved_by': actor.id,
                'approved_date': fields.Datetime.now(),
                'delegated_from_user_id': delegated_from.id if delegated_from else False,
            })
            rec.activity_ids.action_done()
            if not rec._workflow_activate_next(line):
                rec._finish_custom_workflow()
        return True

    def action_submit(self):
        returned = self.filtered(lambda r: r.state == 'returned' and r.workflow_id)
        if returned:
            returned.action_workflow_resubmit()
        drafts = self - returned
        return super(MaterialRequestWorkflowV2, drafts).action_submit() if drafts else True
