from odoo import http, fields, _
from odoo.exceptions import AccessError, ValidationError, UserError
from odoo.http import request, content_disposition
from werkzeug.exceptions import Forbidden

from .portal import EmployeeAdminPortal, BASE


class EmployeeAdminTimesheet(EmployeeAdminPortal):
    @http.route(BASE + '/attendance-timesheet', type='http', auth='user', website=True, methods=['GET', 'POST'], csrf=True)
    def attendance_timesheet(self, company_id=None, employee_id=None, date_from=None, date_to=None, **kw):
        gateway = self._service()
        service = request.env['absar.attendance.timesheet.service']
        try:
            service._check_access()
            company = gateway._company(company_id)
            employees = service._employees(company.id)
        except AccessError as exc:
            raise Forbidden(str(exc))
        today = fields.Date.context_today(gateway)
        values = self._context(gateway, company, kind='attendance', employees=employees,
                               selected_employee=str(employee_id or ''), date_from=date_from or str(today.replace(day=1)),
                               date_to=date_to or str(today), error='')
        if request.httprequest.method == 'POST':
            try:
                # Validate under the real caller before elevating report metadata.
                service._data(company.id, employee_id, date_from, date_to)
                payload = {'company_id': company.id, 'employee_id': employee_id,
                           'date_from': date_from, 'date_to': date_to}
                report = request.env.ref('absar_portal_employee_admin.action_attendance_timesheet_pdf').sudo()
                pdf, _format = report._render_qweb_pdf(report.report_name, res_ids=[], data=payload)
                return request.make_response(pdf, headers=[('Content-Type', 'application/pdf'),
                    ('Content-Disposition', content_disposition('Attendance_Timesheet_%s_%s.pdf' % (date_from, date_to))),
                    ('Cache-Control', 'private, no-store'), ('X-Content-Type-Options', 'nosniff')])
            except AccessError as exc:
                raise Forbidden(str(exc))
            except (ValidationError, UserError) as exc:
                values['error'] = str(exc)
        return request.render('absar_portal_employee_admin.attendance_timesheet_form', values)
