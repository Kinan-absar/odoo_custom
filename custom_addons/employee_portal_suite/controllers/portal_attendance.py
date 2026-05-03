from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
import pytz


def _tz_convert(dt, employee):
    """Convert a naive UTC datetime (as stored by Odoo) to the employee's
    local timezone and return a formatted string like '11:00 AM'."""
    if not dt:
        return ''
    tz_name = (employee and employee.tz) or 'UTC'
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc
    # Odoo stores datetimes as naive UTC — make them timezone-aware then convert
    dt_utc = pytz.utc.localize(dt)
    return dt_utc.astimezone(tz)


def _is_attendance_only():
    """Return True when the current user belongs ONLY to the Attendance Only
    group and should be restricted to /my/employee/attendance."""
    return request.env.user.has_group(
        'employee_portal_suite.group_attendance_only'
    )


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

        # Current open attendance (checked in, not yet checked out)
        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        # Last 10 attendance records
        recent_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
        ], order='check_in desc', limit=10)

        # Today's total worked hours
        tz = pytz.timezone(employee.tz or 'UTC')
        now_local = datetime.now(tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_local.astimezone(pytz.utc).replace(tzinfo=None)

        today_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(today_start_utc)),
        ])

        today_hours = sum(a.worked_hours for a in today_attendances)

        # Success/error message from redirect
        success_message = kw.get('success')
        error_message = kw.get('error')

        return request.render('employee_portal_suite.employee_portal_attendance', {
            'employee': employee,
            'open_attendance': open_attendance,
            'recent_attendances': recent_attendances,
            'today_hours': today_hours,
            'is_checked_in': bool(open_attendance),
            'success_message': success_message,
            'error_message': error_message,
            'page_name': 'attendance',
            'geo_enforce': (
                employee.work_location_id.geo_enforce
                if employee.work_location_id else False
            ),
            # Pass a callable so the XML template can convert UTC → local time.
            # Usage in QWeb: t-esc="fmt_dt(att.check_in, '%I:%M %p')"
            'fmt_dt': lambda dt, fmt='%I:%M %p': (
                _tz_convert(dt, employee).strftime(fmt) if dt else ''
            ),
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

        # ------------------------------------------------------------------
        # Geolocation validation
        # ------------------------------------------------------------------
        work_location = employee.work_location_id
        if work_location and work_location.geo_enforce:
            try:
                emp_lat = float(post.get('geo_lat', ''))
                emp_lon = float(post.get('geo_lon', ''))
            except (TypeError, ValueError):
                # Browser did not send coordinates — reject if enforcement is on
                return request.redirect('/my/employee/attendance?error=geo_required')

            in_range, distance = work_location.check_employee_in_range(emp_lat, emp_lon)
            if not in_range:
                return request.redirect(
                    '/my/employee/attendance?error=geo_out_of_range&distance=%d&radius=%d'
                    % (distance, work_location.geo_radius)
                )

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

        # ------------------------------------------------------------------
        # Geolocation check on check-out (non-blocking: always allow,
        # but flag the record when the employee is outside the allowed zone)
        # ------------------------------------------------------------------
        outside_location = False
        work_location = employee.work_location_id
        if work_location and work_location.geo_enforce:
            try:
                emp_lat = float(post.get('geo_lat', ''))
                emp_lon = float(post.get('geo_lon', ''))
                in_range, _distance = work_location.check_employee_in_range(emp_lat, emp_lon)
                if not in_range:
                    outside_location = True
            except (TypeError, ValueError):
                # Coordinates not provided or invalid — flag conservatively
                outside_location = True

        try:
            vals = {'check_out': fields.Datetime.now()}
            if outside_location:
                vals['checkout_outside_location'] = True
            open_attendance.sudo().write(vals)
            if outside_location:
                return request.redirect('/my/employee/attendance?success=checked_out&warn=outside_location')
            return request.redirect('/my/employee/attendance?success=checked_out')
        except Exception as e:
            return request.redirect('/my/employee/attendance?error=check_out_failed')
