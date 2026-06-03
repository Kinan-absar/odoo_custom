from odoo import models, fields, api
import pytz


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    # ------------------------------------------------------------------
    # FIELD: flagged when employee checked out outside their work location
    # ------------------------------------------------------------------
    checkout_outside_location = fields.Boolean(
        string="Checked Out Outside Location",
        default=False,
        help=(
            "Set to True when an employee submits a check-out from a GPS position "
            "that is outside the allowed radius of their assigned work location."
        ),
        readonly=True,
    )

    # ------------------------------------------------------------------
    # FIELD: flagged when Odoo's auto-checkout cron closed this record
    # ------------------------------------------------------------------
    auto_checked_out = fields.Boolean(
        string="Auto Checked Out",
        default=False,
        readonly=True,
        help=(
            "Set to True when Odoo's automatic checkout closed this record "
            "because the employee forgot to check out manually."
        ),
    )

    # ------------------------------------------------------------------
    # WRITE OVERRIDE — detect system-triggered checkouts
    # ------------------------------------------------------------------
    def write(self, vals):
        """Intercept every write on hr.attendance.

        When check_out is being written on an open record AND the write
        is coming from the system scheduler (uid == superuser, no
        'from_portal_checkout' context key), we flag the record as
        auto_checked_out and post a chatter note on the employee record
        so HR can see it immediately.
        """
        receiving_checkout = 'check_out' in vals and vals['check_out']

        auto_close_candidates = self.env['hr.attendance']
        if receiving_checkout:
            open_records = self.filtered(lambda r: not r.check_out)
            from_portal = self.env.context.get('from_portal_checkout', False)
            from_superuser = self.env.uid == self.env.ref('base.user_root').id
            if open_records and not from_portal and from_superuser:
                auto_close_candidates = open_records

        result = super().write(vals)

        if auto_close_candidates:
            auto_close_candidates.sudo().write({'auto_checked_out': True})
            auto_close_candidates._notify_hr_auto_checkout()

        return result

    # ------------------------------------------------------------------
    # NOTIFICATION: auto-checkout chatter note
    # ------------------------------------------------------------------
    def _notify_hr_auto_checkout(self):
        """Post an internal note on the employee record for each auto-closed attendance."""
        for record in self:
            employee = record.employee_id
            if not employee:
                continue
            check_out_time = record.check_out
            if check_out_time:
                tz_name = employee.tz or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except Exception:
                    tz = pytz.utc
                local_time = pytz.utc.localize(check_out_time).astimezone(tz)
                time_str = local_time.strftime('%d %b %Y at %I:%M %p')
            else:
                time_str = 'unknown time'

            body = (
                '<p>'
                '<strong>&#128337; Automatic Check-out</strong><br/>'
                'Employee <strong>%s</strong> was <strong>automatically checked out</strong> '
                'at <strong>%s</strong> by the system.<br/>'
                'The employee did not manually check out. Please review if needed.'
                '</p>'
            ) % (employee.name, time_str)

            employee.message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                author_id=self.env.ref('base.user_root').partner_id.id,
            )

    # ------------------------------------------------------------------
    # NOTIFICATION: outside-location checkout
    # ------------------------------------------------------------------
    def _notify_hr_outside_checkout(self):
        """Notify HR of outside-location check-outs.
        Posts on the employee record (which always has mail.thread via hr.employee).
        Called by the base.automation server action.
        """
        for record in self:
            employee = record.employee_id
            check_out_time = record.check_out
            if check_out_time:
                tz_name = (employee and employee.tz) or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except Exception:
                    tz = pytz.utc
                local_time = pytz.utc.localize(check_out_time).astimezone(tz)
                time_str = local_time.strftime('%d %b %Y at %I:%M %p')
            else:
                time_str = 'unknown time'

            body = (
                '<p>'
                '<strong>&#9888; Outside Location Check-out</strong><br/>'
                'Employee <strong>%s</strong> checked out at <strong>%s</strong> '
                'from a location <strong>outside their designated work location</strong>.<br/>'
                'Please review their attendance record.'
                '</p>'
            ) % (employee.name, time_str)

            if employee:
                employee.message_post(
                    body=body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_note',
                    author_id=self.env.ref('base.user_root').partner_id.id,
                )
