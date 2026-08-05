from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AbsarApprovalRequest(models.Model):
    _name = 'absar.approval.request'
    _description = 'Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False, index=True)
    workflow_id = fields.Many2one('absar.approval.workflow', required=True, ondelete='restrict', tracking=True, index=True)
    stage_id = fields.Many2one('absar.approval.stage', readonly=True, tracking=True, index=True)
    res_model = fields.Char(required=True, readonly=True, index=True)
    res_id = fields.Many2oneReference(model_field='res_model', required=True, readonly=True, index=True)
    reference = fields.Char(readonly=True, index=True)
    requester_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, readonly=True, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, readonly=True, index=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, readonly=True, tracking=True, index=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    deadline = fields.Datetime(readonly=True, index=True)
    is_overdue = fields.Boolean(compute='_compute_is_overdue', search='_search_is_overdue')
    line_ids = fields.One2many('absar.approval.request.line', 'request_id', readonly=True)
    audit_ids = fields.One2many('absar.approval.audit', 'request_id', readonly=True)
    current_approver_ids = fields.Many2many('res.users', compute='_compute_current_approvers', search='_search_current_approvers')
    can_current_user_approve = fields.Boolean(compute='_compute_permissions')
    can_current_user_reject = fields.Boolean(compute='_compute_permissions')
    can_current_user_withdraw = fields.Boolean(compute='_compute_permissions')
    comment = fields.Text(copy=False)

    _sql_constraints = [
        ('request_resource_required', 'CHECK(res_id > 0)', 'A valid target record is required.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('absar_approval_internal') and not self.env.user.has_group(
                'absar_approval_engine.group_approval_manager'):
            raise AccessError(_('Approval requests must be created from a business document.'))
        sequence = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = sequence.next_by_code('absar.approval.request') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        protected = {
            'workflow_id', 'stage_id', 'res_model', 'res_id', 'reference',
            'requester_id', 'company_id', 'state', 'started_at',
            'completed_at', 'deadline', 'line_ids', 'audit_ids',
        }
        if protected.intersection(vals) and not self.env.context.get('absar_approval_internal'):
            if not self.env.user.has_group('absar_approval_engine.group_approval_manager'):
                raise AccessError(_('Approval control fields can only be changed through workflow actions.'))
        return super().write(vals)

    def _internal_write(self, vals):
        return self.with_context(absar_approval_internal=True).write(vals)

    @api.depends('deadline', 'state')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = bool(rec.state == 'in_progress' and rec.deadline and rec.deadline < now)

    def _search_is_overdue(self, operator, value):
        domain = [('state', '=', 'in_progress'), ('deadline', '<', fields.Datetime.now())]
        return domain if (operator in ('=', '==') and value) or (operator == '!=' and not value) else ['!'] + domain

    @api.depends('line_ids.state', 'line_ids.user_id', 'stage_id')
    def _compute_current_approvers(self):
        for rec in self:
            rec.current_approver_ids = rec.sudo().line_ids.filtered(
                lambda line: line.stage_id == rec.stage_id and line.state == 'pending'
            ).mapped('user_id')

    def _search_current_approvers(self, operator, value):
        """Search the computed current approvers without relational rewriting.

        Returning a domain such as ``('line_ids.user_id', '=', uid)`` is not
        safe here. While traversing the one2many, Odoo may rewrite it into
        ``('user_id', 'in', uid)`` on the line model; ``uid`` is an integer and
        the ``in`` operator requires a collection. Resolve the matching request
        IDs explicitly instead.
        """
        supported = ('=', '==', '!=', '<>', 'in', 'not in')
        if operator not in supported:
            raise UserError(_('Unsupported operator for current approvers: %s') % operator)

        if isinstance(value, models.BaseModel):
            user_ids = value.ids
        elif isinstance(value, (list, tuple, set)):
            user_ids = [item.id if isinstance(item, models.BaseModel) else item for item in value]
        elif value:
            user_ids = [value.id if isinstance(value, models.BaseModel) else value]
        else:
            user_ids = []

        user_ids = [int(user_id) for user_id in user_ids if user_id]
        matching_request_ids = []
        if user_ids:
            lines = self.env['absar.approval.request.line'].sudo().search([
                ('user_id', 'in', user_ids),
                ('state', '=', 'pending'),
                ('request_id.state', '=', 'in_progress'),
            ])
            matching_request_ids = lines.filtered(
                lambda line: line.stage_id == line.request_id.stage_id
            ).mapped('request_id').ids

        negative = operator in ('!=', '<>', 'not in')
        return [('id', 'not in' if negative else 'in', matching_request_ids)]

    @api.depends('state', 'stage_id', 'line_ids.state', 'line_ids.user_id', 'requester_id')
    def _compute_permissions(self):
        user = self.env.user
        for rec in self:
            eligible = rec._get_user_pending_lines(user)
            requester_blocked = rec.requester_id == user and not rec.workflow_id.requester_can_approve
            rec.can_current_user_approve = bool(rec.state == 'in_progress' and eligible and not requester_blocked)
            rec.can_current_user_reject = bool(rec.can_current_user_approve and rec.stage_id.can_reject)
            rec.can_current_user_withdraw = bool(
                rec.state in ('draft', 'in_progress') and rec.requester_id == user and rec.workflow_id.allow_withdraw
            )

    def _target_record(self):
        self.ensure_one()
        return self.env[self.res_model].browse(self.res_id).exists()

    def action_open_target(self):
        self.ensure_one()
        record = self._target_record()
        if not record:
            raise UserError(_('The target record no longer exists.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': self.res_model,
            'res_id': self.res_id, 'view_mode': 'form', 'target': 'current',
        }

    @api.model
    def create_for_record(self, record, workflow=None, requester=None, auto_start=True):
        record.ensure_one()
        workflow = workflow or self.env['absar.approval.workflow'].find_workflow(record)
        if not workflow:
            raise UserError(_('No matching approval workflow was found for %s.') % record.display_name)
        if workflow.model != record._name or not workflow.matches_record(record):
            raise ValidationError(_('The selected workflow does not apply to this record.'))
        company = record.company_id if 'company_id' in record._fields else self.env.company
        request = self.with_context(absar_approval_internal=True).create({
            'workflow_id': workflow.id,
            'res_model': record._name,
            'res_id': record.id,
            'reference': record.display_name,
            'requester_id': (requester or self.env.user).id,
            'company_id': company.id,
        })
        if auto_start:
            request.action_start()
        return request

    def action_start(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft approval requests can be started.'))
            stages = rec.workflow_id.stage_ids.filtered('active').sorted(lambda s: (s.sequence, s.id))
            if not stages:
                raise UserError(_('The workflow has no active approval stages.'))
            rec._internal_write({'state': 'in_progress', 'started_at': fields.Datetime.now(), 'completed_at': False})
            rec._log('started', old_state='draft', new_state='in_progress')
            rec._activate_stage(stages[0])
            rec._notify_target(_('Approval request %s started.') % rec.name)
        return True

    def _activate_stage(self, stage):
        self.ensure_one()
        target = self._target_record()
        if not target:
            raise UserError(_('The target record no longer exists.'))
        users = stage.resolve_approvers(target)
        delegates = self.env['absar.approval.delegation'].delegated_users_for(users, self.workflow_id)
        all_users = users | delegates
        if not all_users:
            raise UserError(_('No active approvers could be resolved for stage %s.') % stage.name)
        deadline = fields.Datetime.now() + timedelta(days=stage.deadline_days) if stage.deadline_days else False
        self._internal_write({'stage_id': stage.id, 'deadline': deadline, 'comment': False})
        values = []
        for user in all_users:
            delegated_from = False
            if user in delegates:
                delegation = self.env['absar.approval.delegation'].sudo().search([
                    ('delegate_id', '=', user.id), ('delegator_id', 'in', users.ids),
                    ('active', '=', True), ('date_from', '<=', fields.Datetime.now()),
                    ('date_to', '>=', fields.Datetime.now()),
                ], limit=1)
                delegated_from = delegation.delegator_id.id
            values.append({
                'request_id': self.id, 'stage_id': stage.id, 'user_id': user.id,
                'delegated_from_id': delegated_from,
            })
        self.env['absar.approval.request.line'].sudo().create(values)
        self._schedule_activities(all_users, stage, deadline)
        self._log('stage_started', stage=stage, old_state=self.state, new_state=self.state)

    def _schedule_activities(self, users, stage, deadline=False):
        self.ensure_one()
        target = self._target_record()
        if not target or not hasattr(target, 'activity_schedule'):
            return
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        for user in users:
            target.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=user.id,
                date_deadline=fields.Date.to_date(deadline) if deadline else fields.Date.today(),
                summary=_('Approval: %s') % stage.name,
                note=_('Approval request %s requires your action.') % self.name,
            )

    def _get_user_pending_lines(self, user):
        self.ensure_one()
        return self.sudo().line_ids.filtered(
            lambda line: line.stage_id == self.stage_id and line.user_id == user and line.state == 'pending'
        )

    def action_approve(self, comment=None, source='backend'):
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError(_('Only in-progress requests can be approved.'))
            lines = rec._get_user_pending_lines(self.env.user)
            if not lines:
                raise AccessError(_('You are not a pending approver for this stage.'))
            if rec.requester_id == self.env.user and not rec.workflow_id.requester_can_approve:
                raise AccessError(_('The requester cannot approve this workflow.'))
            comment = comment if comment is not None else rec.comment
            if rec.stage_id.require_approval_comment and not comment:
                raise ValidationError(_('An approval comment is required.'))
            lines.sudo().write({'state': 'approved', 'action_date': fields.Datetime.now(), 'comment': comment})
            rec._log('delegated' if lines.filtered('delegated_from_id') else 'approved', stage=rec.stage_id,
                     comment=comment, delegated_from=lines[:1].delegated_from_id, source=source)
            rec._finish_user_activity()
            if rec._stage_is_complete():
                rec._complete_stage()
            rec.comment = False
        return True

    def _stage_is_complete(self):
        self.ensure_one()
        lines = self.sudo().line_ids.filtered(lambda line: line.stage_id == self.stage_id)
        approved_count = len(lines.filtered(lambda line: line.state == 'approved'))
        if self.stage_id.approval_mode == 'any':
            return approved_count >= 1
        if self.stage_id.approval_mode == 'all':
            return bool(lines) and approved_count == len(lines)
        return approved_count >= self.stage_id.minimum_approvals

    def _complete_stage(self):
        self.ensure_one()
        self.sudo().line_ids.filtered(
            lambda line: line.stage_id == self.stage_id and line.state == 'pending'
        ).sudo().write({'state': 'skipped'})
        self._close_stage_activities()
        self._log('stage_approved', stage=self.stage_id)
        stages = self.workflow_id.stage_ids.filtered('active').sorted(lambda s: (s.sequence, s.id))
        next_stages = stages.filtered(lambda stage: (stage.sequence, stage.id) > (self.stage_id.sequence, self.stage_id.id))
        if next_stages:
            self._activate_stage(next_stages[0])
        else:
            self._internal_write({'state': 'approved', 'completed_at': fields.Datetime.now(), 'deadline': False})
            self._log('approved', old_state='in_progress', new_state='approved')
            self._notify_target(_('Approval request %s was fully approved.') % self.name)
            target = self._target_record()
            if target and hasattr(target, '_approval_engine_approved'):
                target._approval_engine_approved(self)

    def action_reject(self, comment=None, source='backend'):
        for rec in self:
            if rec.state != 'in_progress' or not rec.stage_id.can_reject:
                raise UserError(_('This request cannot be rejected at its current stage.'))
            lines = rec._get_user_pending_lines(self.env.user)
            if not lines:
                raise AccessError(_('You are not a pending approver for this stage.'))
            comment = comment if comment is not None else rec.comment
            if rec.stage_id.require_rejection_comment and not comment:
                raise ValidationError(_('A rejection reason is required.'))
            lines.sudo().write({'state': 'rejected', 'action_date': fields.Datetime.now(), 'comment': comment})
            rec.sudo().line_ids.filtered(lambda line: line.state == 'pending').sudo().write({'state': 'skipped'})
            rec._internal_write({'state': 'rejected', 'completed_at': fields.Datetime.now(), 'deadline': False, 'comment': False})
            rec._close_stage_activities()
            rec._log('rejected', stage=rec.stage_id, old_state='in_progress', new_state='rejected', comment=comment, source=source)
            rec._notify_target(_('Approval request %(name)s was rejected: %(reason)s', name=rec.name, reason=comment))
            target = rec._target_record()
            if target and hasattr(target, '_approval_engine_rejected'):
                target._approval_engine_rejected(rec, comment)
        return True

    def action_withdraw(self):
        for rec in self:
            if rec.requester_id != self.env.user or not rec.workflow_id.allow_withdraw:
                raise AccessError(_('Only the requester can withdraw this request.'))
            if rec.state not in ('draft', 'in_progress'):
                raise UserError(_('Only draft or in-progress requests can be withdrawn.'))
            old_state = rec.state
            rec.sudo().line_ids.filtered(lambda line: line.state == 'pending').sudo().write({'state': 'skipped'})
            rec._internal_write({'state': 'withdrawn', 'completed_at': fields.Datetime.now(), 'deadline': False})
            rec._close_stage_activities()
            rec._log('withdrawn', old_state=old_state, new_state='withdrawn')
        return True

    def action_cancel(self):
        if not self.env.user.has_group('absar_approval_engine.group_approval_manager'):
            raise AccessError(_('Only Approval Managers can cancel requests.'))
        for rec in self.filtered(lambda r: r.state not in ('approved', 'cancelled')):
            old_state = rec.state
            rec.sudo().line_ids.filtered(lambda line: line.state == 'pending').sudo().write({'state': 'skipped'})
            rec._internal_write({'state': 'cancelled', 'completed_at': fields.Datetime.now(), 'deadline': False})
            rec._close_stage_activities()
            rec._log('cancelled', old_state=old_state, new_state='cancelled')
        return True

    def _finish_user_activity(self):
        self.ensure_one()
        target = self._target_record()
        if not target or not hasattr(target, 'activity_ids'):
            return
        activities = target.activity_ids.filtered(
            lambda act: act.user_id == self.env.user and act.summary == _('Approval: %s') % self.stage_id.name
        )
        activities.action_feedback(feedback=_('Approval action completed.'))

    def _close_stage_activities(self):
        self.ensure_one()
        target = self._target_record()
        if not target or not hasattr(target, 'activity_ids'):
            return
        activities = target.activity_ids.filtered(lambda act: act.summary == _('Approval: %s') % self.stage_id.name)
        activities.unlink()

    def _notify_target(self, body):
        self.ensure_one()
        target = self._target_record()
        if target and hasattr(target, 'message_post'):
            target.message_post(body=body, subtype_xmlid='mail.mt_note')

    def _log(self, action, stage=None, old_state=None, new_state=None, comment=None,
             delegated_from=None, source='backend'):
        self.ensure_one()
        return self.env['absar.approval.audit'].sudo().create({
            'request_id': self.id,
            'stage_id': stage.id if stage else False,
            'action': action,
            'user_id': self.env.user.id,
            'old_state': old_state,
            'new_state': new_state,
            'comment': comment,
            'source': source,
            'delegated_from_id': delegated_from.id if delegated_from else False,
        })

    @api.model
    def _cron_mark_overdue(self):
        overdue = self.search([
            ('state', '=', 'in_progress'), ('deadline', '!=', False),
            ('deadline', '<', fields.Datetime.now()),
        ])
        already_logged = self.env['absar.approval.audit'].sudo().search([
            ('request_id', 'in', overdue.ids), ('action', '=', 'overdue'), ('stage_id', 'in', overdue.stage_id.ids),
        ]).mapped(lambda log: (log.request_id.id, log.stage_id.id))
        for rec in overdue:
            if (rec.id, rec.stage_id.id) not in already_logged:
                rec._log('overdue', stage=rec.stage_id, source='system')


class AbsarApprovalRequestLine(models.Model):
    _name = 'absar.approval.request.line'
    _description = 'Approval Request Approver'
    _order = 'stage_id, id'

    request_id = fields.Many2one('absar.approval.request', required=True, ondelete='cascade', index=True)
    workflow_id = fields.Many2one(related='request_id.workflow_id', store=True, index=True)
    stage_id = fields.Many2one('absar.approval.stage', required=True, ondelete='restrict', index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='restrict', index=True)
    delegated_from_id = fields.Many2one('res.users', ondelete='set null')
    state = fields.Selection([
        ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('skipped', 'Skipped'),
    ], default='pending', required=True, readonly=True, index=True)
    action_date = fields.Datetime(readonly=True)
    comment = fields.Text(readonly=True)
    company_id = fields.Many2one(related='request_id.company_id', store=True, index=True)

    _sql_constraints = [
        ('request_stage_user_uniq', 'unique(request_id, stage_id, user_id)',
         'A user can appear only once in an approval stage.'),
    ]
