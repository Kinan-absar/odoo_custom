from odoo import models, fields
import pytz


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    checkout_outside_location = fields.Boolean(
        string="Checked Out Outside Location",
        default=False,
        help=(
            "Set to True when an employee submits a check-out from a GPS position "
            "that is outside the allowed radius of their assigned work location."
        ),
        readonly=True,
    )

    def _notify_hr_outside_checkout(self):
        """Post an internal chatter note on each flagged attendance record.
        Called by the base.automation server action — must not use import statements.
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
                'Please review this attendance record.'
                '</p>'
            ) % (employee.name, time_str)

            record.message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                author_id=self.env.ref('base.user_root').partner_id.id,
            )
