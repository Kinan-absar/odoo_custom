# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request, content_disposition
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class EmployeePortalSalaryReport(CustomerPortal):
    """Read-only portal access for the Employee Portal: Salary Report Viewer group."""

    def _check_salary_report_viewer(self):
        return request.env.user.has_group('employee_portal_suite.group_salary_report_viewer')

    def _salary_report_domain(self):
        return [('state', 'in', ['generated', 'batch_created'])]

    @http.route('/my/employee/salary-reports', type='http', auth='user', website=True)
    def portal_salary_reports(self, page=1, **kw):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        Report = request.env['employee.attendance.salary.report'].sudo()
        domain = self._salary_report_domain()
        total = Report.search_count(domain)
        pager = portal_pager(
            url='/my/employee/salary-reports',
            total=total,
            page=page,
            step=20,
        )
        reports = Report.search(domain, order='date_from desc, id desc', limit=20, offset=pager['offset'])

        # Clear the "new report" badge on the dashboard now that the user has
        # opened the list. Next badge only appears once a newer report is added.
        request.env['portal.report.seen'].sudo()._mark_seen(request.env.user.id, 'salary_report')

        return request.render('employee_portal_suite.portal_salary_report_list', {
            'reports': reports,
            'pager': pager,
            'page_name': 'salary_reports',
        })

    @http.route('/my/employee/salary-reports/<int:report_id>', type='http', auth='user', website=True)
    def portal_salary_report_detail(self, report_id, **kw):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        report = request.env['employee.attendance.salary.report'].sudo().browse(report_id)
        if not report.exists() or report.state not in ('generated', 'batch_created'):
            return request.not_found()

        return request.render('employee_portal_suite.portal_salary_report_detail', {
            'report': report,
            'groups': report._get_work_location_groups(),
            'page_name': 'salary_reports',
        })

    @http.route('/my/employee/salary-reports/<int:report_id>/print', type='http', auth='user', website=True)
    def portal_salary_report_print(self, report_id, **kw):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        report = request.env['employee.attendance.salary.report'].sudo().browse(report_id)
        if not report.exists() or report.state not in ('generated', 'batch_created'):
            return request.not_found()

        pdf, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'employee_portal_suite.report_salary_summary_template', [report.id]
        )
        filename = 'Salary Report - %s to %s.pdf' % (report.date_from, report.date_to)
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(pdf, headers=headers)
