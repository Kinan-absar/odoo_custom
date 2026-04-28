# -*- coding: utf-8 -*-

import csv
import io

from odoo import http
from odoo.http import request


class AttendancePayrollExportController(http.Controller):

    @http.route('/attendance/payroll/mudad/<int:report_id>', type='http', auth='user')
    def export_mudad(self, report_id, **kwargs):
        report = request.env['attendance.payroll.report'].browse(report_id).exists()
        if not report:
            return request.not_found()
        lines, warnings = report._mudad_lines_and_warnings()
        content = '\n'.join(lines)
        filename = 'Mudad_WPS_%s_%s.txt' % (report.date_from.strftime('%Y%m%d'), report.date_to.strftime('%Y%m%d'))
        headers = [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(content, headers=headers)

    @http.route('/attendance/payroll/csv/<int:report_id>', type='http', auth='user')
    def export_csv(self, report_id, **kwargs):
        report = request.env['attendance.payroll.report'].browse(report_id).exists()
        if not report:
            return request.not_found()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Employee', 'Department', 'On Leave', 'Shifts', 'Expected Days', 'Days Worked', 'Absent Days',
            'Adjusted Absent Days', 'Total Hours', 'Standard Hours', 'Hour Diff', 'Gross Salary',
            'Hourly Deduction', 'Absent Deduction', 'Fixed Deductions', 'Other Deductions',
            'Overtime Pay', 'Reimbursements', 'Total Deductions', 'Net Salary'
        ])
        for line in report.line_ids:
            writer.writerow([
                line.employee_id.name, line.department_id.name or '', 'Yes' if line.is_on_leave else 'No',
                line.shift_count, line.expected_days, line.days_worked, line.absent_days, line.adjusted_absent_days,
                round(line.total_hours, 2), line.standard_hours, round(line.hour_diff, 2), round(line.gross_salary, 2),
                round(line.hourly_deduction, 2), round(line.absent_deduction, 2), round(line.fixed_deductions, 2),
                round(line.other_deductions, 2), round(line.overtime_pay, 2), round(line.reimbursements, 2),
                round(line.total_deductions, 2), round(line.net_salary, 2),
            ])
        filename = 'Attendance_Payroll_%s_%s.csv' % (report.date_from.strftime('%Y%m%d'), report.date_to.strftime('%Y%m%d'))
        headers = [
            ('Content-Type', 'text/csv; charset=utf-8'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
        ]
        return request.make_response(output.getvalue(), headers=headers)
