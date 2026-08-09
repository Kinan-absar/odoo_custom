import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class EmployeePortalTelegramConfigNotifications(models.Model):
    _inherit = 'employee.portal.telegram.config'

    requester_stage_notifications = fields.Boolean(
        string='Notify Requester on Stage Changes', default=True,
        help='Notify the requesting employee when an Employee Request or Material Request moves to a new approval stage.'
    )
    approval_reminders_enabled = fields.Boolean(
        string='Approval Reminders', default=True,
        help='Send Telegram reminders while a request is waiting for approval.'
    )
    approval_reminder_hours = fields.Integer(
        string='First Reminder After (Hours)', default=24,
    )
    approval_repeat_hours = fields.Integer(
        string='Repeat Reminder Every (Hours)', default=24,
    )
    approval_escalation_hours = fields.Integer(
        string='Escalate After (Hours)', default=48,
    )
    approval_escalation_user_id = fields.Many2one(
        'res.users', string='Escalation Recipient',
        domain="[('share', '=', False)]",
        help='Optional internal user who receives one escalation notice when an approval remains pending beyond the escalation threshold.'
    )

    attendance_reminders_enabled = fields.Boolean(
        string='Attendance Reminders', default=True,
    )
    clock_in_before_minutes = fields.Integer(
        string='Clock-In Reminder Before Start (Minutes)', default=15,
    )
    missing_clock_in_after_minutes = fields.Integer(
        string='Missing Clock-In Reminder After Start (Minutes)', default=30,
    )
    clock_out_before_minutes = fields.Integer(
        string='Clock-Out Reminder Before End (Minutes)', default=15,
    )
    missing_clock_out_after_minutes = fields.Integer(
        string='Missing Clock-Out Reminder After End (Minutes)', default=60,
    )


class ResUsersTelegramAttendanceState(models.Model):
    _inherit = 'res.users'

    telegram_clockin_pre_date = fields.Date(copy=False, readonly=True)
    telegram_clockin_late_date = fields.Date(copy=False, readonly=True)
    telegram_clockout_pre_date = fields.Date(copy=False, readonly=True)
    telegram_clockout_missing_date = fields.Date(copy=False, readonly=True)


class HrAttendanceTelegramReminders(models.Model):
    _inherit = 'hr.attendance'

    @api.model
    def _config(self):
        return self.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
            ('attendance_reminders_enabled', '=', True),
        ], order='id desc', limit=1)

    @api.model
    def _scheduled_bounds(self, employee, local_now):
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        if not calendar:
            return False, False

        weekday = str(local_now.weekday())
        local_date = local_now.date()
        lines = calendar.attendance_ids.filtered(
            lambda line: line.dayofweek == weekday
            and not getattr(line, 'display_type', False)
            and (not line.date_from or line.date_from <= local_date)
            and (not line.date_to or line.date_to >= local_date)
        )
        if not lines:
            return False, False

        # For ordinary schedules, earliest start and latest end define the workday.
        # Split shifts are handled by spanning both work periods.
        start_hour = min(lines.mapped('hour_from'))
        end_hour = max(lines.mapped('hour_to'))

        def from_float(hour_float):
            hours = int(hour_float)
            minutes = int(round((hour_float - hours) * 60))
            if minutes >= 60:
                hours += 1
                minutes -= 60
            if hours >= 24:
                return datetime.combine(local_date + timedelta(days=1), time.min)
            return datetime.combine(local_date, time(hour=hours, minute=minutes))

        return from_float(start_hour), from_float(end_hour)

    @api.model
    def _utc_day_bounds(self, tz, local_date):
        start_local = tz.localize(datetime.combine(local_date, time.min))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(pytz.utc).replace(tzinfo=None),
            end_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _send(self, user, title, body):
        return self.env['employee.portal.telegram.service'].sudo().send_to_user(
            user, title, body, '/my/employee/attendance'
        )

    @api.model
    def cron_send_attendance_reminders(self):
        config = self._config()
        if not config:
            return

        users = self.env['res.users'].sudo().search([
            ('active', '=', True),
            ('telegram_chat_id', '!=', False),
        ])
        now_utc = fields.Datetime.now()

        for user in users:
            employee = user.employee_id
            if not employee:
                continue
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if not calendar:
                continue

            tz_name = calendar.tz or employee.tz or user.tz or 'UTC'
            try:
                tz = pytz.timezone(tz_name)
            except Exception:
                tz = pytz.utc

            aware_utc = pytz.utc.localize(now_utc)
            local_now = aware_utc.astimezone(tz)
            local_date = local_now.date()
            start_naive, end_naive = self._scheduled_bounds(employee, local_now)
            if not start_naive or not end_naive:
                continue

            start_local = tz.localize(start_naive)
            end_local = tz.localize(end_naive)
            day_start_utc, day_end_utc = self._utc_day_bounds(tz, local_date)

            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', day_start_utc),
                ('check_in', '<', day_end_utc),
            ])
            has_checked_in = bool(attendances)
            open_attendance = attendances.filtered(lambda a: not a.check_out)[:1]

            before_in = start_local - timedelta(minutes=max(config.clock_in_before_minutes, 0))
            after_in = start_local + timedelta(minutes=max(config.missing_clock_in_after_minutes, 0))
            before_out = end_local - timedelta(minutes=max(config.clock_out_before_minutes, 0))
            after_out = end_local + timedelta(minutes=max(config.missing_clock_out_after_minutes, 0))

            # Cron normally runs every 10 minutes. A 12-minute window prevents duplicate/missed pre-reminders.
            window = timedelta(minutes=12)

            if (
                not has_checked_in
                and user.telegram_clockin_pre_date != local_date
                and before_in <= local_now < before_in + window
            ):
                if self._send(
                    user,
                    'Clock-in reminder',
                    f'Your scheduled workday starts at {start_local.strftime("%I:%M %p")}. Please remember to check in.'
                ):
                    user.sudo().write({'telegram_clockin_pre_date': local_date})

            if (
                not has_checked_in
                and user.telegram_clockin_late_date != local_date
                and local_now >= after_in
                and local_now < end_local
            ):
                if self._send(
                    user,
                    'Missing clock-in',
                    f'No check-in was found for today. Your scheduled start time was {start_local.strftime("%I:%M %p")}.'
                ):
                    user.sudo().write({'telegram_clockin_late_date': local_date})

            if (
                open_attendance
                and user.telegram_clockout_pre_date != local_date
                and before_out <= local_now < before_out + window
            ):
                if self._send(
                    user,
                    'Clock-out reminder',
                    f'Your scheduled workday ends at {end_local.strftime("%I:%M %p")}. Please remember to check out before leaving.'
                ):
                    user.sudo().write({'telegram_clockout_pre_date': local_date})

            if (
                open_attendance
                and user.telegram_clockout_missing_date != local_date
                and local_now >= after_out
            ):
                if self._send(
                    user,
                    'Missing clock-out',
                    f'You are still checked in after your scheduled end time of {end_local.strftime("%I:%M %p")}. Please check out if you have finished work.'
                ):
                    user.sudo().write({'telegram_clockout_missing_date': local_date})


class TelegramApprovalReminderMixin(models.AbstractModel):
    _name = 'employee.portal.telegram.approval.mixin'
    _description = 'Telegram Approval Reminder Mixin'

    telegram_stage_entered_at = fields.Datetime(copy=False, readonly=True)
    telegram_last_approval_reminder_at = fields.Datetime(copy=False, readonly=True)
    telegram_approval_reminder_count = fields.Integer(default=0, copy=False, readonly=True)
    telegram_escalation_sent = fields.Boolean(default=False, copy=False, readonly=True)

    def _telegram_approval_states(self):
        return []

    def _telegram_stage_label(self):
        selection = dict(self._fields['state'].selection)
        return selection.get(self.state, self.state)

    def _telegram_requester_user(self):
        self.ensure_one()
        return self.employee_id.user_id if self.employee_id else False

    def _telegram_current_approvers(self):
        return self.env['res.users']

    def _telegram_approval_path(self):
        return '/my/employee'

    def _telegram_requester_path(self):
        return '/my/employee'

    def write(self, vals):
        state_change = 'state' in vals
        new_state = vals.get('state')
        if state_change and new_state in self._telegram_approval_states():
            vals = dict(vals)
            vals.update({
                'telegram_stage_entered_at': fields.Datetime.now(),
                'telegram_last_approval_reminder_at': False,
                'telegram_approval_reminder_count': 0,
                'telegram_escalation_sent': False,
            })
        result = super().write(vals)

        if state_change and new_state in self._telegram_approval_states():
            config = self.env['employee.portal.telegram.config'].sudo().search([
                ('active', '=', True), ('enabled', '=', True),
            ], order='id desc', limit=1)
            if config and config.requester_stage_notifications:
                service = self.env['employee.portal.telegram.service'].sudo()
                for rec in self:
                    requester = rec._telegram_requester_user()
                    if requester:
                        service.send_to_user(
                            requester,
                            f'{rec.name} status updated',
                            f'Your request is now at: {rec._telegram_stage_label()}.',
                            rec._telegram_requester_path(),
                        )
        return result

    @api.model
    def _cron_approval_reminders_for_model(self):
        """Process only reminders/escalations that are actually due.

        The previous implementation loaded every request in an approval state on
        every cron run.  On a busy database that could keep the scheduled action
        alive long enough to block module upgrades.  This version uses date
        domains, small batches and records an attempted reminder timestamp so a
        temporarily unreachable Telegram recipient cannot be retried in a tight
        loop every cron cycle.
        """
        config = self.env['employee.portal.telegram.config'].sudo().search([
            ('active', '=', True),
            ('enabled', '=', True),
            ('approval_reminders_enabled', '=', True),
        ], order='id desc', limit=1)
        if not config:
            return

        states = self._telegram_approval_states()
        if not states:
            return

        now = fields.Datetime.now()
        first_after = timedelta(hours=max(config.approval_reminder_hours, 1))
        repeat_after = timedelta(hours=max(config.approval_repeat_hours, 1))
        escalate_after = timedelta(hours=max(config.approval_escalation_hours, 1))
        first_cutoff = now - first_after
        repeat_cutoff = now - repeat_after
        service = self.env['employee.portal.telegram.service'].sudo()

        entered_due = [
            '|',
            '&', ('telegram_stage_entered_at', '!=', False), ('telegram_stage_entered_at', '<=', first_cutoff),
            '&', ('telegram_stage_entered_at', '=', False), ('write_date', '<=', first_cutoff),
        ]
        reminder_due = [
            '|',
            ('telegram_last_approval_reminder_at', '=', False),
            ('telegram_last_approval_reminder_at', '<=', repeat_cutoff),
        ]
        reminder_domain = [('state', 'in', states)] + entered_due + reminder_due

        # A small batch is intentional: approval reminders are not time-critical
        # to the minute, and keeping cron runs short is more important on Odoo.sh.
        records = self.sudo().search(
            reminder_domain,
            order='telegram_last_approval_reminder_at asc, telegram_stage_entered_at asc, id asc',
            limit=25,
        )

        for rec in records:
            entered = rec.telegram_stage_entered_at or rec.write_date or rec.create_date
            sent_any = False
            for user in rec._telegram_current_approvers():
                sent_any = service.send_to_user(
                    user,
                    'Approval still pending',
                    f'{rec.name} has been waiting for {rec._telegram_stage_label()} since {fields.Datetime.to_string(entered)}.',
                    rec._telegram_approval_path(),
                ) or sent_any

            vals = {'telegram_last_approval_reminder_at': now}
            if sent_any:
                vals['telegram_approval_reminder_count'] = rec.telegram_approval_reminder_count + 1
            rec.sudo().write(vals)

        # Escalation is a separate, small query so it is not delayed by the
        # repeat-reminder interval.  Nothing is escalated unless a recipient is set.
        if config.approval_escalation_user_id:
            escalation_cutoff = now - escalate_after
            escalation_entered_due = [
                '|',
                '&', ('telegram_stage_entered_at', '!=', False), ('telegram_stage_entered_at', '<=', escalation_cutoff),
                '&', ('telegram_stage_entered_at', '=', False), ('write_date', '<=', escalation_cutoff),
            ]
            escalation_domain = [
                ('state', 'in', states),
                ('telegram_escalation_sent', '=', False),
            ] + escalation_entered_due
            escalation_records = self.sudo().search(
                escalation_domain,
                order='telegram_stage_entered_at asc, id asc',
                limit=25,
            )
            for rec in escalation_records:
                if service.send_to_user(
                    config.approval_escalation_user_id,
                    'Approval escalation',
                    f'{rec.name} is still waiting for {rec._telegram_stage_label()} and has exceeded the configured escalation time.',
                    rec._telegram_approval_path(),
                ):
                    rec.sudo().write({'telegram_escalation_sent': True})


class EmployeeRequestTelegramReminders(models.Model):
    _inherit = ['employee.request', 'employee.portal.telegram.approval.mixin']
    _name = 'employee.request'

    def _telegram_approval_states(self):
        return ['manager', 'hr', 'finance', 'ceo']

    def _telegram_current_approvers(self):
        self.ensure_one()
        if self.state == 'manager':
            return self.manager_id.user_id if self.manager_id and self.manager_id.user_id else self.env['res.users']
        groups = {
            'hr': 'employee_portal_suite.group_employee_portal_hr',
            'finance': 'employee_portal_suite.group_employee_portal_finance',
            'ceo': 'employee_portal_suite.group_employee_portal_ceo',
        }
        group = self.env.ref(groups.get(self.state), raise_if_not_found=False) if groups.get(self.state) else False
        return group.users if group else self.env['res.users']

    def _telegram_approval_path(self):
        self.ensure_one()
        return f'/my/employee/approvals/{self.id}'

    def _telegram_requester_path(self):
        self.ensure_one()
        return f'/my/employee/requests/{self.id}'

    @api.model
    def cron_send_telegram_approval_reminders(self):
        self._cron_approval_reminders_for_model()
        self.env['material.request']._cron_approval_reminders_for_model()


class MaterialRequestTelegramReminders(models.Model):
    _inherit = ['material.request', 'employee.portal.telegram.approval.mixin']
    _name = 'material.request'

    def _telegram_approval_states(self):
        return ['purchase', 'store', 'project_manager', 'director', 'ceo']

    def _telegram_current_approvers(self):
        self.ensure_one()
        if self.state == 'store':
            return self.store_manager_user_id if self.store_manager_user_id else self.env['res.users']
        if self.state == 'project_manager':
            return self.project_manager_user_id if self.project_manager_user_id else self.env['res.users']
        groups = {
            'purchase': 'employee_portal_suite.group_mr_purchase_rep',
            'director': 'employee_portal_suite.group_mr_projects_director',
            'ceo': 'employee_portal_suite.group_employee_portal_ceo',
        }
        group = self.env.ref(groups.get(self.state), raise_if_not_found=False) if groups.get(self.state) else False
        return group.users if group else self.env['res.users']

    def _telegram_approval_path(self):
        self.ensure_one()
        return f'/my/employee/material/approvals/{self.id}'

    def _telegram_requester_path(self):
        self.ensure_one()
        return f'/my/employee/material/{self.id}'
