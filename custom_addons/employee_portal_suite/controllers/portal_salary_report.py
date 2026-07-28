# -*- coding: utf-8 -*-

from odoo import http, _
from odoo.http import request, content_disposition
import io
import xlsxwriter
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class EmployeePortalSalaryReport(CustomerPortal):
    """Portal access for salary report viewing and controlled line adjustments."""

    def _check_salary_report_viewer(self):
        return request.env.user.has_group('employee_portal_suite.group_salary_report_viewer')

    def _salary_report_domain(self):
        return [('state', 'in', ['generated', 'batch_created'])]

    def _get_portal_salary_report(self, report_id):
        report = request.env['employee.attendance.salary.report'].sudo().browse(report_id)
        if not report.exists() or report.state not in ('generated', 'batch_created'):
            return False
        return report

    def _parse_amount(self, value):
        try:
            return float((value or '0').replace(',', '').strip())
        except (TypeError, ValueError):
            return 0.0

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
            'can_edit_salary_lines': not report.batch_created,
        })

    @http.route('/my/employee/salary-reports/<int:report_id>/lines/<int:line_id>/update', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_salary_report_line_update(self, report_id, line_id, **post):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        report = self._get_portal_salary_report(report_id)
        if not report:
            return request.not_found()
        if report.batch_created:
            return request.redirect('/my/employee/salary-reports/%s?locked=1' % report.id)

        line = request.env['employee.attendance.salary.report.line'].sudo().browse(line_id)
        if not line.exists() or line.report_id.id != report.id:
            return request.not_found()

        line.write({
            'other_deductions': max(self._parse_amount(post.get('other_deductions')), 0.0),
            'reimbursements': max(self._parse_amount(post.get('reimbursements')), 0.0),
        })
        return request.redirect('/my/employee/salary-reports/%s?updated=1' % report.id)

    @http.route('/my/employee/salary-reports/<int:report_id>/lines/<int:line_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_salary_report_line_delete(self, report_id, line_id, **post):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        report = self._get_portal_salary_report(report_id)
        if not report:
            return request.not_found()
        if report.batch_created:
            return request.redirect('/my/employee/salary-reports/%s?locked=1' % report.id)

        line = request.env['employee.attendance.salary.report.line'].sudo().browse(line_id)
        if not line.exists() or line.report_id.id != report.id:
            return request.not_found()

        line.unlink()
        return request.redirect('/my/employee/salary-reports/%s?deleted=1' % report.id)

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


    @http.route('/my/employee/salary-reports/<int:report_id>/excel', type='http', auth='user', website=True)
    def portal_salary_report_excel(self, report_id, **kw):
        if not self._check_salary_report_viewer():
            return request.redirect('/my/employee')

        report = self._get_portal_salary_report(report_id)
        if not report:
            return request.not_found()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Salary Report')

        title_format = workbook.add_format({
            'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter'
        })
        subtitle_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter'
        })
        header_format = workbook.add_format({
            'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'bg_color': '#D9EAF7'
        })
        text_format = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        number_format = workbook.add_format({'border': 1, 'num_format': '#,##0.00', 'align': 'right'})
        subtotal_text = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#F2F2F2'})
        subtotal_number = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#F2F2F2',
            'num_format': '#,##0.00', 'align': 'right'
        })
        total_text = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#D9D9D9'})
        total_number = workbook.add_format({
            'bold': True, 'border': 1, 'bg_color': '#D9D9D9',
            'num_format': '#,##0.00', 'align': 'right'
        })

        worksheet.merge_range('A1:H1', report.name or _('Salary Report'), title_format)
        worksheet.merge_range(
            'A2:H2',
            _('Period: %s to %s') % (report.date_from, report.date_to),
            subtitle_format,
        )
        worksheet.write_row(3, 0, [
            '#', _('Work Location'), _('Employee'), _('Gross Salary'),
            _('Attendance Deduction'), _('Other Deductions'),
            _('Reimbursements'), _('Net Salary')
        ], header_format)

        row = 4
        sequence = 0
        groups = report._get_work_location_groups()
        for group in groups:
            for line in group['lines']:
                sequence += 1
                worksheet.write_number(row, 0, sequence, text_format)
                worksheet.write(row, 1, group['name'], text_format)
                worksheet.write(row, 2, line.employee_id.name or '', text_format)
                worksheet.write_number(row, 3, line.gross_salary, number_format)
                worksheet.write_number(row, 4, line.attendance_deduction, number_format)
                worksheet.write_number(row, 5, line.other_deductions, number_format)
                worksheet.write_number(row, 6, line.reimbursements, number_format)
                worksheet.write_number(row, 7, line.net_salary, number_format)
                row += 1

            worksheet.merge_range(row, 0, row, 2, _('Subtotal - %s') % group['name'], subtotal_text)
            worksheet.write_number(row, 3, group['gross_salary'], subtotal_number)
            worksheet.write_number(row, 4, sum(group['lines'].mapped('attendance_deduction')), subtotal_number)
            worksheet.write_number(row, 5, sum(group['lines'].mapped('other_deductions')), subtotal_number)
            worksheet.write_number(row, 6, group['reimbursements'], subtotal_number)
            worksheet.write_number(row, 7, group['net_salary'], subtotal_number)
            row += 1

        worksheet.merge_range(row, 0, row, 2, _('Grand Total'), total_text)
        worksheet.write_number(row, 3, report.total_gross_salary, total_number)
        worksheet.write_number(row, 4, report.total_attendance_deductions, total_number)
        worksheet.write_number(row, 5, report.total_other_deductions, total_number)
        worksheet.write_number(row, 6, report.total_reimbursements, total_number)
        worksheet.write_number(row, 7, report.total_net_salary, total_number)

        worksheet.freeze_panes(4, 0)
        worksheet.autofilter(3, 0, max(row - 1, 3), 7)
        worksheet.set_column('A:A', 6)
        worksheet.set_column('B:B', 22)
        worksheet.set_column('C:C', 28)
        worksheet.set_column('D:H', 20)
        worksheet.set_row(0, 24)

        workbook.close()
        output.seek(0)
        filename = 'Salary Report - %s to %s.xlsx' % (report.date_from, report.date_to)
        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Length', len(output.getvalue())),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(output.getvalue(), headers=headers)
