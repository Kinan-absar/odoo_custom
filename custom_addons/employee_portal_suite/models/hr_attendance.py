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

        When check_out is being set on a record that currently has no
        check_out AND the write is NOT coming from a human user (i.e. the
        uid is the OdooBot / superuser, which is what Odoo's scheduled
        actions run as), we mark the record as auto_checked_out and post
        a chatter note so HR can see it immediately.

        The portal check-in/out routes use sudo() which also runs as
        superuser, so we distinguish them by checking whether check_out
        was supplied by our own portal controller.  We do that via a
        context key `from_portal_checkout` that the controller sets;
        if that key is absent AND the user is the system user, we treat
        the write as an automatic one.
        """
        # Identify records that are open (no check_out yet) and are now
        # receiving a check_out value in this write.
        receiving_checkout = (
            'check_out' in vals
            and vals['check_out']  # not being cleared
        )

        auto_close_candidates = self.env['hr.attendance']
        if receiving_checkout:
            # Only flag records that have no check_out yet
            auto_close_candidates = self.filtered(lambda r: not r.check_out)

            # Determine whether this write is coming from the system scheduler.
            # Portal controller sets context key 'from_portal_checkout' = True.
            # Human backend users have uid != SUPERUSER_ID in normal sessions,
            # but scheduled actions always run as SUPERUSER_ID without that key.
            from_portal = self.env.context.get('from_portal_checkout', False)
            from_superuser = self.env.uid == self.env.ref('base.user_root').id

            if from_portal or not from_superuser:
                # Normal portal checkout or a human admin editing the record —
                # do not flag as auto checkout.
                auto_close_candidates = self.env['hr.attendance']

        # Perform the actual write first so check_out is stored
        result = super().write(vals)

        # Now flag and notify for any auto-closed records
        if auto_close_candidates:
            auto_close_candidates.sudo().write({'auto_checked_out': True})
            auto_close_candidates._notify_hr_auto_checkout()

        return result

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

            body = (
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
        """Post an internal chatter note on each flagged attendance record.
        Called by the base.automation server action.
        """
        for record in self:
            employee = record.employee_id
            check_out_time = record.check_out
            if check_out_time:
                tz_name = (employee and employee.tz) or 'UTC'\


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
