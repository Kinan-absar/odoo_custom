from odoo import models, fields, api, _
from odoo.exceptions import UserError


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

    # ---------------------------------------------------------
    # STATE MACHINE
    # ---------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
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

    # ---------------------------------------------------------
    # SEQUENCE ASSIGN
    # ---------------------------------------------------------
    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('employee.request.seq') or _('New')
        return super().create(vals)

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
        if not user or not user.partner_id.email:
            return
        mail_values = {
            'subject': subject,
            'body_html': f"<p>{body}</p>",
            'email_to': user.partner_id.email,
            'author_id': self.env.user.partner_id.id,
        }
        self.env['mail.mail'].sudo().create(mail_values).send()

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
            rec.message_post(body=f"{new_state.capitalize()} stage approved.")
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

    # ---------------------------------------------------------
    # USER ACTIONS
    # ---------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))

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
        self._advance_state(
            new_state='hr',
            group_xmlid='employee_portal_suite.group_employee_portal_hr',
            approved_user_field='manager_approved_by',
            approved_date_field='manager_approved_date'
        )

    def action_hr_approve(self):
        self._advance_state(
            new_state='finance',
            group_xmlid='employee_portal_suite.group_employee_portal_finance',
            approved_user_field='hr_approved_by',
            approved_date_field='hr_approved_date'
        )

    def action_finance_approve(self):
        self._advance_state(
            new_state='ceo',
            group_xmlid='employee_portal_suite.group_employee_portal_ceo',
            approved_user_field='finance_approved_by',
            approved_date_field='finance_approved_date'
        )

    def action_ceo_approve(self):
        for rec in self:
            if rec.state != 'ceo':
                raise UserError(_("Request is not in CEO approval stage."))

            rec.ceo_approved_by = self.env.user.id
            rec.ceo_approved_date = fields.Datetime.now()
            rec.state = 'approved'
            rec.message_post(body="Request fully approved.")
            rec._close_activities()

            if rec.employee_id.user_id:
                rec._notify_user(
                    rec.employee_id.user_id,
                    "Request Approved",
                    f"Your request {rec.name} has been approved."
                )

    # ---------------------------------------------------------
    # REJECTION ACTION — FIXED
    # ---------------------------------------------------------
    def action_reject(self):
        for rec in self:

            if rec.state == 'approved':
                raise UserError(_("Approved requests cannot be rejected."))

            # Store rejection source stage & user
            rec.state_before_reject = rec.state
            rec.rejected_by = rec.env.user.id

            rec.state = 'rejected'
            rec.message_post(body="Request rejected.")
            rec._close_activities()

            if rec.employee_id.user_id:
                rec._notify_user(
                    rec.employee_id.user_id,
                    "Request Rejected",
                    f"Your request {rec.name} has been rejected."
                )

    # ---------------------------------------------------------
    # PORTAL TIMELINE
    # ---------------------------------------------------------
    def get_portal_timeline(self):
        self.ensure_one()
        timeline = []

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
