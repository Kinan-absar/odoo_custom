from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta
import pytz


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
        except Exception as e:
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
        except Exception as e:
            return request.redirect('/my/employee/attendance?error=check_out_failed')
