from odoo import models, fields, api
from markupsafe import Markup
import pytz
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


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
    # FIELD: flagged when our custom auto-checkout cron closed this record
    # ------------------------------------------------------------------
    auto_checked_out = fields.Boolean(
        string="Auto Checked Out",
        default=False,
        readonly=True,
        help=(
            "Set to True when the system automatically checked out this employee "
            "because they forgot to check out manually."
        ),
    )

    # ------------------------------------------------------------------
    # WRITE OVERRIDE — detect portal vs. system checkouts
    #
    # BUG FIX: The previous version had an inverted condition that caused
    # the auto_checked_out flag to fire on portal checkouts and miss
    # actual system-driven checkouts.
    #
    # NEW LOGIC (clear and explicit):
    #   - Portal checkout  → context key 'from_portal_checkout' = True  → NOT auto
    #   - Our cron method  → context key 'from_auto_checkout'   = True  → IS auto
    #   - Any other write  → treated as manual/backend edit               → NOT auto
    #
    # We no longer rely on uid == SUPERUSER_ID since sudo() is used
    # everywhere and makes that check unreliable.
    # ------------------------------------------------------------------
    def write(self, vals):
        receiving_checkout = (
            'check_out' in vals
            and vals['check_out']
        )

        auto_close_candidates = self.env['hr.attendance']

        if receiving_checkout:
            open_records = self.filtered(lambda r: not r.check_out)

            # Only flag as auto-checked-out when our own cron sets this key
            if self.env.context.get('from_auto_checkout'):
                auto_close_candidates = open_records

        result = super().write(vals)

        if auto_close_candidates:
            # Use direct write to avoid triggering this override recursively
            super(HrAttendance, auto_close_candidates).write({'auto_checked_out': True})
            auto_close_candidates._notify_hr_auto_checkout()

        return result

    # ------------------------------------------------------------------
    # CUSTOM AUTO-CHECKOUT CRON
    #
    # Why we need this instead of Odoo's built-in:
    #   1. Odoo's native "Automatic Check-Out" cron SKIPS employees who
    #      have a flexible working schedule or NO schedule set at all.
    #      Portal-only employees typically fall into this category, so
    #      they are completely ignored by the native cron.
    #   2. The native cron reads the employee's work schedule to determine
    #      an appropriate checkout time — it cannot handle employees who
    #      don't have a resource.calendar set.
    #   3. Our cron uses a simple configurable tolerance (hours) and
    #      applies to ALL employees with an open attendance, regardless
    #      of their work schedule.
    #
    # Configurable via ir.config_parameter:
    #   employee_portal_suite.auto_checkout_hours  (default: 10)
    # ------------------------------------------------------------------
    @api.model
    def _auto_checkout_open_attendances(self):
        """Close all attendance records that are still open at end of day
        in Riyadh time (Asia/Riyadh, UTC+3).

        Called by the ir.cron defined in data/attendance_automation.xml
        which is scheduled to run daily at 11:50 PM Riyadh time (20:50 UTC).

        Any attendance record with no check_out and a check_in before
        today's end-of-day in Riyadh time will be closed at the exact
        moment the cron runs.
        """
        riyadh_tz = pytz.timezone('Asia/Riyadh')

        # Current time in Riyadh
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        now_riyadh = now_utc.astimezone(riyadh_tz)

        # End of today in Riyadh = 23:59:59 today
        end_of_day_riyadh = now_riyadh.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        # Convert end-of-day back to UTC for the DB query (Odoo stores UTC)
        end_of_day_utc = end_of_day_riyadh.astimezone(pytz.utc).replace(tzinfo=None)

        # Find all open attendance records checked in before end of today
        open_attendances = self.sudo().search([
            ('check_out', '=', False),
            ('check_in', '<=', fields.Datetime.to_string(end_of_day_utc)),
        ])

        if not open_attendances:
            _logger.info("Auto-checkout cron: no open attendance records found.")
            return

        _logger.info(
            "Auto-checkout cron: closing %d open attendance record(s) "
            "at end of day (Riyadh time: %s).",
            len(open_attendances),
            now_riyadh.strftime('%Y-%m-%d %H:%M:%S %Z'),
        )

        checkout_time = fields.Datetime.now()

        # Write with our context key so write() flags them correctly
        open_attendances.with_context(from_auto_checkout=True).write({
            'check_out': checkout_time,
        })

    # ------------------------------------------------------------------
    # NOTIFICATION: post chatter note on auto-closed records
    # ------------------------------------------------------------------
    def _notify_hr_auto_checkout(self):
        """Post an internal chatter note on each auto-checked-out record."""
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

            body = Markup(
                '<p>'
                '<strong>&#128337; Automatic Check-out</strong><br/>'
                'Employee <strong>%s</strong> was <strong>automatically checked out</strong> '
                'at <strong>%s</strong> by the system.<br/>'
                'The employee did not manually check out. Please review if needed.'
                '</p>'
            ) % (employee.name if employee else '(unknown)', time_str)

            record.message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                author_id=self.env.ref('base.user_root').partner_id.id,
            )

    # ------------------------------------------------------------------
    # NOTIFICATION: outside-location checkout (unchanged)
    # ------------------------------------------------------------------
    def _notify_hr_outside_checkout(self):
        """Post an internal chatter note on each flagged attendance record."""
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

            body = Markup(
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
