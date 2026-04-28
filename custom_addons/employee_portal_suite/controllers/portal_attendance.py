from odoo import http, fields
from odoo.http import request
from datetime import datetime
import pytz


def _to_local(dt, tz):
    """Convert a naive UTC datetime to a timezone-aware local datetime."""
    if not dt:
        return None
    return pytz.utc.localize(dt).astimezone(tz)


class EmployeePortalAttendance(http.Controller):

    # ---------------------------------------------------------
    # ATTENDANCE PAGE
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance', type='http', auth='user', website=True)
    def portal_attendance(self, **kw):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        # Resolve employee timezone (fall back to user tz, then UTC)
        tz_name = employee.tz or user.tz or 'UTC'
        tz = pytz.timezone(tz_name)

        # Current open attendance (checked in, not yet checked out)
        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        # Last 10 attendance records
        raw_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
        ], order='check_in desc', limit=10)

        # Convert each record's datetimes to local time for display
        recent_attendances = []
        for a in raw_attendances:
            recent_attendances.append({
                'check_in_local': _to_local(a.check_in, tz),
                'check_out_local': _to_local(a.check_out, tz),
                'worked_hours': a.worked_hours,
                'is_open': not a.check_out,
            })

        # Today's total worked hours (compare against local midnight -> UTC)
        now_local = datetime.now(tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_local.astimezone(pytz.utc).replace(tzinfo=None)

        today_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(today_start_utc)),
        ])
        today_hours = sum(a.worked_hours for a in today_attendances)

        # Localized check-in time for the hero card
        open_checkin_local = _to_local(open_attendance.check_in, tz) if open_attendance else None

        # Success/error message from redirect
        success_message = kw.get('success')
        error_message = kw.get('error')

        return request.render('employee_portal_suite.employee_portal_attendance', {
            'employee': employee,
            'open_attendance': open_attendance,
            'open_checkin_local': open_checkin_local,
            'recent_attendances': recent_attendances,
            'today_hours': today_hours,
            'is_checked_in': bool(open_attendance),
            'success_message': success_message,
            'error_message': error_message,
            'page_name': 'attendance',
            'tz_name': tz_name,
        })

    # ---------------------------------------------------------
    # CHECK-IN
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance/check_in', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_attendance_check_in(self, **post):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        # Prevent double check-in
        existing = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if existing:
            return request.redirect('/my/employee/attendance?error=already_checked_in')

        try:
            request.env['hr.attendance'].sudo().create({
                'employee_id': employee.id,
                'check_in': fields.Datetime.now(),
            })
            return request.redirect('/my/employee/attendance?success=checked_in')
        except Exception:
            return request.redirect('/my/employee/attendance?error=check_in_failed')

    # ---------------------------------------------------------
    # CHECK-OUT
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance/check_out', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_attendance_check_out(self, **post):
        user = request.env.user
        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if not open_attendance:
            return request.redirect('/my/employee/attendance?error=not_checked_in')

        try:
            open_attendance.sudo().write({
                'check_out': fields.Datetime.now(),
            })
            return request.redirect('/my/employee/attendance?success=checked_out')
        except Exception:
            return request.redirect('/my/employee/attendance?error=check_out_failed')
