from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import datetime
from dateutil.relativedelta import relativedelta

class EmployeePortalRedirect(CustomerPortal):

    @http.route(['/my'], type='http', auth='user', website=True)
    def account(self, **kw):
        """Redirect employees away from customer portal."""
        user = request.env.user

        # Employees → always redirect to employee portal
        if user.employee_id:
            return request.redirect('/my/employee')

        # Customers/vendors → normal Odoo portal
        return super().account(**kw)


    @http.route(['/my/home'], type='http', auth='user', website=True)
    def home_redirect(self, **kw):
        """Override My Account page. Employees should never land here."""
        user = request.env.user

        # Employees → force employee dashboard
        if user.employee_id:
            return request.redirect('/my/employee')

        # Normal customers/vendors → default portal home
        return super().account(**kw)
    
class EmployeePortalAttendance(http.Controller):

    @http.route(['/my/attendance'], type='http', auth='user', website=True)
    def portal_attendance(self, **kwargs):

        employee = request.env.user.employee_id

        today = datetime.today().date()

        # Today's attendance
        today_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', today),
        ], limit=1)

        # Monthly hours
        first_day_month = today.replace(day=1)

        monthly_records = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', first_day_month),
        ])

        total_hours = 0
        for rec in monthly_records:
            if rec.check_out:
                total_hours += rec.worked_hours

        values = {
            'today_attendance': today_attendance,
            'monthly_hours': round(total_hours, 2),
        }

        return request.render(
            'employee_portal_suite.portal_attendance_page',
            values
        )
