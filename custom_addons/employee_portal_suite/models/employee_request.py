from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv import expression
import base64


class EmployeeRequest(models.Model):
    _name = 'employee.request'
    _description = 'Employee Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # ---------------------------------------------------------
    # BASIC FIELDS
    # ---------------------------------------------------------
    name = fields.Char(
        string='Request Number',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )

    manager_id = fields.Many2one(
        'hr.employee',
        string='Direct Manager',
        compute='_compute_manager',
        store=True,
        readonly=True,
        tracking=True
    )

    request_type = fields.Selection([
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
    ], string='Request Type', required=True, tracking=True)

    description = fields.Text(string='Description')

    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        tracking=True
    )

    leave_from = fields.Date(string="Leave From")
    leave_to = fields.Date(string="Leave To")
    time_off_type_id = fields.Many2one(
        'hr.leave.type',
        string='Time Off Type',
        tracking=True,
        help='Odoo Time Off type to use when creating the approved leave.'
    )
    time_off_id = fields.Many2one(
        'hr.leave',
        string='Created Time Off',
        readonly=True,
        copy=False,
        tracking=True
    )


    # ---------------------------------------------------------
    # CONFIGURABLE WORKFLOW
    # ---------------------------------------------------------
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True,
        help='Optional project used to resolve a project-specific approval workflow.'
    )
    workflow_id = fields.Many2one(
        'employee.portal.workflow', string='Approval Workflow', readonly=True, copy=False, tracking=True
    )
    approval_line_ids = fields.One2many(
        'employee.portal.workflow.approval.line', 'employee_request_id',
        string='Workflow Approval Steps', readonly=True, copy=False
    )
    current_approval_line_id = fields.Many2one(
        'employee.portal.workflow.approval.line',
        string='Current Approval Step', compute='_compute_current_approval_line', store=False
    )

    # ---------------------------------------------------------
    # STATE MACHINE
    # ---------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('workflow', 'Workflow Approval'),
        ('manager', 'Manager Approval'),
        ('hr', 'HR Approval'),
        ('finance', 'Finance Approval'),
        ('ceo', 'CEO Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)

    # Tracking who approved which stage
    manager_approved_by = fields.Many2one("res.users", string="Manager Approved By")
    hr_approved_by = fields.Many2one("res.users", string="HR Approved By")
    finance_approved_by = fields.Many2one("res.users", string="Finance Approved By")
    ceo_approved_by = fields.Many2one("res.users", string="CEO Approved By")

    # ---------------------------------------------------------
    # APPROVAL METADATA
    # ---------------------------------------------------------
    manager_approved_by = fields.Many2one('res.users', readonly=True)
    manager_approved_date = fields.Datetime(readonly=True)
    manager_comment = fields.Text()

    hr_approved_by = fields.Many2one('res.users', readonly=True)
    hr_approved_date = fields.Datetime(readonly=True)
    hr_comment = fields.Text()

    finance_approved_by = fields.Many2one('res.users', readonly=True)
    finance_approved_date = fields.Datetime(readonly=True)
    finance_comment = fields.Text()

    ceo_approved_by = fields.Many2one('res.users', readonly=True)
    ceo_approved_date = fields.Datetime(readonly=True)
    ceo_comment = fields.Text()

    # ---------------------------------------------------------
    # REJECTION METADATA (NEW)
    # ---------------------------------------------------------
    state_before_reject = fields.Char()
    rejected_by = fields.Many2one('res.users')

    # ---------------------------------------------------------
    # COMPUTE MANAGER
    # ---------------------------------------------------------
    @api.depends('employee_id')
    def _compute_manager(self):
        for rec in self:
            rec.manager_id = rec.employee_id.parent_id
   
   #employee autofilled
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'employee_id' in fields_list:
            employee = self.env.user.employee_id
            if not employee:
                raise UserError(_("Your user is not linked to an employee."))
            res['employee_id'] = employee.id
        return res
    # ---------------------------------------------------------
    # SEQUENCE ASSIGN
    # ---------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('employee.request.seq') or _('New')
        return super().create(vals_list)

    # ---------------------------------------------------------
    # DISPLAY LABEL
    # ---------------------------------------------------------
    def get_request_type_display(self):
        labels = dict(self._fields['request_type'].selection)
        return labels.get(self.request_type, self.request_type)

    # ---------------------------------------------------------
    # NOTIFICATION HELPERS
    # ---------------------------------------------------------
    def _notify_user(self, user, subject, body):
        if not user:
            return
        if user.partner_id.email:
            mail_values = {
                'subject': subject,
                'body_html': f"<p>{body}</p>",
                'email_to': user.partner_id.email,
                'author_id': self.env.user.partner_id.id,
            }
            self.env['mail.mail'].sudo().create(mail_values).send()
        self.env['employee.portal.telegram.service'].sudo().send_to_user(
            user, subject, body, f"/my/employee/approvals/{self.id}"
        )

    def _schedule_activity(self, user, summary, note):
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=user.id,
            summary=summary,
            note=note
        )

    def _close_activities(self):
        self.activity_ids.action_done()

    # ---------------------------------------------------------
    # GENERIC STATE ADVANCE
    # ---------------------------------------------------------
    def _advance_state(self, new_state, group_xmlid, approved_user_field, approved_date_field):
        for rec in self:
            rec[approved_user_field] = self.env.user.id
            rec[approved_date_field] = fields.Datetime.now()

            rec.state = new_state
            rec._close_activities()

            # Notify next group
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
            if group:
                for user in group.users:
                    rec._notify_user(
                        user,
                        f"Request {rec.name} requires your approval",
                        f"Request {rec.name} is awaiting your action."
                    )
                    rec._schedule_activity(
                        user,
                        "Approval Needed",
                        f"Please review request {rec.name}."
                    )
                    #helper

    @api.depends('approval_line_ids.state')
    def _compute_current_approval_line(self):
        for rec in self:
            rec.current_approval_line_id = rec.approval_line_ids.filtered(lambda l: l.state == 'pending')[:1]

    def _resolve_custom_workflow(self):
        self.ensure_one()
        return self.env['employee.portal.workflow'].sudo().resolve_workflow(
            'employee_request', project=self.project_id, employee_request_type=self.request_type,
            company=(self.project_id.company_id if self.project_id else self.employee_id.company_id)
        )

    def _notify_workflow_line(self, line):
        self.ensure_one()
        for user in line.sudo().approver_user_ids:
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

    def _start_custom_workflow(self, workflow):
        self.ensure_one()
        steps = workflow.sudo().step_ids.sorted(lambda step: (step.sequence, step.id))
        if not steps:
            raise UserError(_('The selected workflow has no approval steps.'))

        line_model = self.env['employee.portal.workflow.approval.line'].sudo()
        values = []
        for index, step in enumerate(steps):
            users = step.sudo().resolve_users(self)
            if not users:
                raise UserError(_(
                    'Workflow step "%s" has no approver. Check the project responsible employee, role users, or specific user.'
                ) % step.name)
            role_name = (step.approval_role_id.name if step.approval_role_id else (step.role_assignment_id.name if step.role_assignment_id else False))
            values.append({
                'employee_request_id': self.id,
                'workflow_id': workflow.id,
                'source_step_id': step.id,
                'sequence': step.sequence,
                'name': step.name,
                'approver_type': step.approver_type,
                'role_name': role_name,
                'approver_user_ids': [(6, 0, users.ids)],
                'state': 'pending' if index == 0 else 'waiting',
            })
        self.sudo().approval_line_ids.unlink()
        lines = line_model.create(values)
        self.sudo().write({'workflow_id': workflow.id, 'state': 'workflow'})
        self.message_post(body=_('Request submitted using workflow: %s') % workflow.display_name)
        self._close_activities()
        self._notify_workflow_line(lines.filtered(lambda l: l.state == 'pending')[:1])

    def _finish_custom_workflow(self):
        self.ensure_one()
        self.sudo().write({'state': 'approved'})
        self._send_final_pdf_and_notify_all(
            report_xmlid='employee_portal_suite.employee_request_pdf',
            subject=f'Request {self.name} – Fully Approved',
            body=f'Request {self.name} has been fully approved. Please find the attached document.'
        )
        self.message_post(body=_('Request fully approved through configurable workflow.'))
        self._close_activities()
        if self.employee_id.user_id:
            self.env['employee.portal.telegram.service'].sudo().send_to_user(
                self.employee_id.user_id,
                f'Request {self.name} approved',
                f'Your request {self.name} has been fully approved.',
                f'/my/employee/requests/{self.id}'
            )

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
            line.write({
                'state': 'approved',
                'approved_by': actor.id,
                'approved_date': fields.Datetime.now(),
            })
            rec._close_activities()
            next_line = rec.approval_line_ids.sudo().filtered(lambda l: l.state == 'waiting').sorted(lambda l: (l.sequence, l.id))[:1]
            if next_line:
                next_line.write({'state': 'pending'})
                rec.message_post(body=_('Workflow step approved: %s. Next step: %s.') % (line.name, next_line.name))
                rec._notify_workflow_line(next_line)
            else:
                rec._finish_custom_workflow()
        return True

    def action_workflow_reject(self):
        for rec in self:
            if rec.state != 'workflow':
                raise UserError(_('This request is not in configurable workflow approval.'))
            line = rec.current_approval_line_id.sudo()
            actor = self.env['res.users'].browse(self.env.context.get('workflow_actor_user_id')) or self.env.user
            if not line or not line.can_user_approve(actor):
                raise UserError(_('You are not allowed to reject the current workflow step.'))
            line.write({
                'state': 'rejected',
                'rejected_by': actor.id,
                'rejected_date': fields.Datetime.now(),
            })
            rec.sudo().write({
                'state_before_reject': 'workflow',
                'rejected_by': actor.id,
                'state': 'rejected',
            })
            rec.message_post(body=_('Request rejected at workflow step: %s') % line.name)
            rec._close_activities()
        return True

    @api.model
    def _portal_visibility_domain(self, user=None):
        """Return the UNION of every Employee Request role the user has.

        Broad functional roles intentionally widen visibility.  A user who is
        both Manager and Finance must not be trapped by the Manager
        subordinate-only scope.
        """
        user = user or self.env.user

        broad_groups = (
            "employee_portal_suite.group_employee_portal_hr",
            "employee_portal_suite.group_employee_portal_finance",
            "employee_portal_suite.group_employee_portal_ceo",
            "employee_portal_suite.group_employee_portal_admin",
        )
        if any(user.has_group(group) for group in broad_groups):
            return []

        domains = [[("approval_line_ids.approver_user_ids", "in", [user.id])]]
        if user.has_group("employee_portal_suite.group_employee_portal_employee"):
            domains.append([("employee_id.user_id", "=", user.id)])

        if user.has_group("employee_portal_suite.group_employee_portal_manager"):
            domains.append([
                "|",
                ("manager_id.user_id", "=", user.id),
                ("employee_id.user_id", "=", user.id),
            ])

        return expression.OR(domains) if domains else [("id", "=", 0)]

    def _portal_can_view(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        domain = self._portal_visibility_domain(user)
        if not domain:
            return True
        return bool(self.sudo().search_count(expression.AND([[('id', '=', self.id)], domain])))

    def _portal_can_approve(self, user=None):
        self.ensure_one()
        user = user or self.env.user

        if self.state == 'workflow':
            line = self.current_approval_line_id.sudo()
            return bool(line and line.can_user_approve(user))

        # Super Administrator is an explicit workflow override role.
        if user.has_group("employee_portal_suite.group_employee_portal_superadmin"):
            return self.state in {"manager", "hr", "finance", "ceo"}

        if self.state == "manager":
            return bool(
                user.has_group("employee_portal_suite.group_employee_portal_manager")
                and self.manager_id.user_id == user
            )
        stage_groups = {
            "hr": "employee_portal_suite.group_employee_portal_hr",
            "finance": "employee_portal_suite.group_employee_portal_finance",
            "ceo": "employee_portal_suite.group_employee_portal_ceo",
        }
        group = stage_groups.get(self.state)
        return bool(group and user.has_group(group))

    def _check_approval(self, required_state, required_group):
        self.ensure_one()

        if self.state != required_state:
            raise UserError(_("This action is not allowed in the current state."))

        # Super Administrator can deliberately override any pending approval stage.
        if self.env.user.has_group("employee_portal_suite.group_employee_portal_superadmin"):
            return

        if required_state == "manager":
            if not (
                self.env.user.has_group(required_group)
                and self.manager_id.user_id == self.env.user
            ):
                raise UserError(_("Only this employee's assigned manager can approve this request."))
            return

        if not self.env.user.has_group(required_group):
            raise UserError(_("You are not allowed to approve at this stage."))

    # ---------------------------------------------------------
    # USER ACTIONS
    # ---------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))

            workflow = rec._resolve_custom_workflow()
            if workflow:
                rec._start_custom_workflow(workflow)
                continue

            rec.state = 'manager'
            rec.message_post(body="Request submitted.")
            rec._close_activities()

            if rec.manager_id.user_id:
                rec._notify_user(
                    rec.manager_id.user_id,
                    "New Request Awaiting Approval",
                    f"A new request {rec.name} requires your review."
                )
                rec._schedule_activity(
                    rec.manager_id.user_id,
                    "Manager Approval Needed",
                    f"Request {rec.name} has been submitted."
                )

    def action_manager_approve(self):
        for rec in self:
            rec._check_approval(
                required_state="manager",
                required_group="employee_portal_suite.group_employee_portal_manager"
            )

            rec._advance_state(
                new_state="hr",
                group_xmlid="employee_portal_suite.group_employee_portal_hr",
                approved_user_field="manager_approved_by",
                approved_date_field="manager_approved_date"
            )

    def action_hr_approve(self):
        for rec in self:
            rec._check_approval(
                required_state="hr",
                required_group="employee_portal_suite.group_employee_portal_hr"
            )

            rec._advance_state(
                new_state="finance",
                group_xmlid="employee_portal_suite.group_employee_portal_finance",
                approved_user_field="hr_approved_by",
                approved_date_field="hr_approved_date"
            )

    def action_finance_approve(self):
        for rec in self:
            rec._check_approval(
                required_state="finance",
                required_group="employee_portal_suite.group_employee_portal_finance"
            )

            rec._advance_state(
                new_state="ceo",
                group_xmlid="employee_portal_suite.group_employee_portal_ceo",
                approved_user_field="finance_approved_by",
                approved_date_field="finance_approved_date"
            )

    def action_ceo_approve(self):
        for rec in self:
            rec._check_approval(
                required_state="ceo",
                required_group="employee_portal_suite.group_employee_portal_ceo"
            )

            rec.ceo_approved_by = self.env.user.id
            rec.ceo_approved_date = fields.Datetime.now()
            rec.state = 'approved'
            rec._send_final_pdf_and_notify_all(
                report_xmlid="employee_portal_suite.employee_request_pdf",
                subject=f"Request {rec.name} – Fully Approved",
                body=f"Request {rec.name} has been fully approved. Please find the attached document."
            )

            rec.message_post(body="Request fully approved.")
            rec._close_activities()
            if rec.employee_id.user_id:
                rec.env['employee.portal.telegram.service'].sudo().send_to_user(
                    rec.employee_id.user_id,
                    f"Request {rec.name} approved",
                    f"Your request {rec.name} has been fully approved.",
                    f"/my/employee/requests/{rec.id}"
                )

    # ---------------------------------------------------------
    # CREATE ODOO TIME OFF FROM AN APPROVED LEAVE REQUEST
    # ---------------------------------------------------------
    def action_create_time_off(self):
        self.ensure_one()

        if not (
            self.env.user.has_group('employee_portal_suite.group_employee_portal_hr')
            or self.env.user.has_group('employee_portal_suite.group_employee_portal_admin')
            or self.env.user.has_group('employee_portal_suite.group_employee_portal_superadmin')
        ):
            raise UserError(_("Only HR, Administrator, or Super Administrator can create Time Off from an Employee Request."))

        if self.request_type != 'leave':
            raise UserError(_("Time Off can only be created from a Leave Request."))
        if self.state != 'approved':
            raise UserError(_("The Leave Request must be fully approved before creating Time Off."))
        if self.time_off_id:
            raise UserError(_("Time Off has already been created for this Leave Request."))
        if not self.leave_from or not self.leave_to:
            raise UserError(_("Please set both Leave From and Leave To dates first."))
        if self.leave_from > self.leave_to:
            raise UserError(_("Leave From cannot be after Leave To."))
        if not self.time_off_type_id:
            raise UserError(_("Please select a Time Off Type before creating the Time Off record."))

        leave = self.env['hr.leave'].sudo().create({
            'name': self.description or _("Employee Request %s") % self.name,
            'employee_id': self.employee_id.id,
            'holiday_status_id': self.time_off_type_id.id,
            'request_date_from': self.leave_from,
            'request_date_to': self.leave_to,
            'employee_request_id': self.id,
        })
        self.write({'time_off_id': leave.id})
        self.message_post(
            body=_("Time Off %(leave)s was created from this approved Leave Request.", leave=leave.display_name)
        )

        # Reload the current form so the linked Time Off appears immediately
        # and the Create Time Off button disappears without reopening the record.
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_open_time_off(self):
        self.ensure_one()
        if not self.time_off_id:
            raise UserError(_("No Time Off record has been created for this request yet."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Time Off'),
            'res_model': 'hr.leave',
            'view_mode': 'form',
            'res_id': self.time_off_id.id,
            'target': 'current',
        }

    # ---------------------------------------------------------
    # REJECTION ACTION — FIXED
    # ---------------------------------------------------------
    def action_reject(self):
        for rec in self:
            stage_group_map = {
                "manager": "employee_portal_suite.group_employee_portal_manager",
                "hr": "employee_portal_suite.group_employee_portal_hr",
                "finance": "employee_portal_suite.group_employee_portal_finance",
                "ceo": "employee_portal_suite.group_employee_portal_ceo",
            }

            required_group = stage_group_map.get(rec.state)
            if not required_group:
                raise UserError(_("This request cannot be rejected at this stage."))

            if not self.env.user.has_group(required_group):
                raise UserError(_("You are not allowed to reject this request."))
            if rec.state == "manager" and rec.manager_id.user_id != self.env.user:
                raise UserError(_("Only this employee's assigned manager can reject this request."))

            rec.state_before_reject = rec.state
            rec.rejected_by = self.env.user.id
            rec.state = 'rejected'
            rec._send_final_pdf_and_notify_all(
                report_xmlid="employee_portal_suite.employee_request_pdf",
                subject=f"Request {rec.name} – Rejected",
                body=f"Request {rec.name} has been rejected. Please find the attached document."
            )


            rec.message_post(body="Request rejected.")
            rec._close_activities()
            if rec.employee_id.user_id:
                rec.env['employee.portal.telegram.service'].sudo().send_to_user(
                    rec.employee_id.user_id,
                    f"Request {rec.name} rejected",
                    f"Your request {rec.name} has been rejected.",
                    f"/my/employee/requests/{rec.id}"
                )

    def get_rejection_reason(self):
        self.ensure_one()
        comments = {
            "manager": self.manager_comment,
            "hr": self.hr_comment,
            "finance": self.finance_comment,
            "ceo": self.ceo_comment,
        }
        if self.state_before_reject == 'workflow':
            rejected_line = self.approval_line_ids.filtered(lambda l: l.state == 'rejected')[:1]
            return rejected_line.comment if rejected_line else ''
        return comments.get(self.state_before_reject) or ""

    # ---------------------------------------------------------
    # PORTAL TIMELINE
    # ---------------------------------------------------------
    def get_portal_timeline(self):
        self.ensure_one()
        timeline = []

        if self.workflow_id:
            for line in self.approval_line_ids.sorted(lambda l: (l.sequence, l.id)):
                if line.state == 'approved':
                    timeline.append({
                        'stage': line.name,
                        'approved_by': line.approved_by.name if line.approved_by else '',
                        'date': line.approved_date,
                        'comment': line.comment or '',
                    })
                elif line.state == 'rejected':
                    timeline.append({
                        'stage': f'{line.name} - Rejected',
                        'approved_by': line.rejected_by.name if line.rejected_by else '',
                        'date': line.rejected_date,
                        'comment': line.comment or '',
                    })
            return timeline

        # Normal approval stages
        stages = [
            ('manager', "Manager Approval", self.manager_approved_by, self.manager_approved_date, self.manager_comment),
            ('hr', "HR Approval", self.hr_approved_by, self.hr_approved_date, self.hr_comment),
            ('finance', "Finance Approval", self.finance_approved_by, self.finance_approved_date, self.finance_comment),
            ('ceo', "CEO Approval", self.ceo_approved_by, self.ceo_approved_date, self.ceo_comment),
        ]

        # Add approvals
        for state, label, user, date, comment in stages:
            if date:
                timeline.append({
                    'stage': label,
                    'approved_by': user.name if user else '',
                    'date': date,
                    'comment': comment or '',
                })

        # Add rejection block
        if self.state == 'rejected':
            stage_labels = {
                'manager': "Manager Stage",
                'hr': "HR Stage",
                'finance': "Finance Stage",
                'ceo': "CEO Stage",
            }

            comments = {
                'manager': self.manager_comment,
                'hr': self.hr_comment,
                'finance': self.finance_comment,
                'ceo': self.ceo_comment,
            }

            stage_label = stage_labels.get(self.state_before_reject, "Unknown Stage")
            comment = comments.get(self.state_before_reject) or "No comment"

            timeline.append({
                'stage': f"{stage_label} - Rejected",
                'approved_by': self.rejected_by.name if self.rejected_by else '',
                'date': self.write_date,
                'comment': comment,
            })

        return timeline

    @api.model
    def retrieve_dashboard(self):
        data = {
            'all_count': self.search_count([]),
            'draft_count': self.search_count([('state', '=', 'draft')]),
            'workflow_count': self.search_count([('state', '=', 'workflow')]),
            'manager_count': self.search_count([('state', '=', 'manager')]),
            'hr_count': self.search_count([('state', '=', 'hr')]),
            'finance_count': self.search_count([('state', '=', 'finance')]),
            'ceo_count': self.search_count([('state', '=', 'ceo')]),
            'approved_count': self.search_count([('state', '=', 'approved')]),
            'rejected_count': self.search_count([('state', '=', 'rejected')]),
            'leave_count': self.search_count([('request_type', '=', 'leave')]),
            'advance_count': self.search_count([('request_type', '=', 'advance')]),
            'other_count': self.search_count([('request_type', '=', 'other')]),
            'my_count': self.search_count([('create_uid', '=', self.env.user.id)]),
        }
        return data

    def get_readable_status(self):
        mapping = {
            "manager": "Pending Manager",
            "hr": "Pending HR",
            "finance": "Pending Finance",
            "ceo": "Pending CEO",
            "approved": "Fully Approved",
            "rejected": "Rejected",
        }
        return mapping.get(self.state, "Unknown")

    def _send_final_pdf_and_notify_all(self, report_xmlid, subject, body):
        self.ensure_one()

        # --------------------------------------------------
        # 1) Render PDF
        # --------------------------------------------------
        report = self.env.ref(report_xmlid)
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            report.id, [self.id]
        )

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f"{self.name}.pdf",
            'type': 'binary',
            'datas': base64.b64encode(pdf_content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })

        # --------------------------------------------------
        # 2) Collect users / emails
        # --------------------------------------------------
        partners = set()
        emails = set()

        def _add_user(user):
            if not user or not user.partner_id:
                return
            partners.add(user.partner_id.id)
            if user.partner_id.email:
                emails.add(user.partner_id.email)

        # Requester
        if self.employee_id.user_id:
            _add_user(self.employee_id.user_id)

        # Approvers
        approver_fields = [
            'manager_approved_by',
            'hr_approved_by',
            'finance_approved_by',
            'purchase_approved_by',
            'store_approved_by',
            'project_manager_approved_by',
            'director_approved_by',
            'ceo_approved_by',
        ]

        for field in approver_fields:
            if field in self._fields:
                _add_user(getattr(self, field))

        # --------------------------------------------------
        # 4) EMAIL (SMTP) with PDF
        # --------------------------------------------------
        if emails:
            mail = self.env['mail.mail'].sudo().create({
                'subject': subject,
                'body_html': f"<p>{body}</p>",
                'email_to': ",".join(emails),
                'attachment_ids': [(4, attachment.id)],
                'author_id': self.env.user.partner_id.id,
            })
            mail.send()

