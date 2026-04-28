import csv
import io
from odoo import http
from odoo.http import request, content_disposition


class AttendancePayrollExport(http.Controller):

    @http.route('/attendance/payroll/export/csv/<int:report_id>',
                type='http', auth='user')
    def export_csv(self, report_id, **kw):
        report = request.env['attendance.payroll.report'].browse(report_id)
        if not report.exists():
            return request.not_found()

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            'Employee', 'Department',
            'Shifts', 'Days Worked', 'Absent Days', 'Flagged',
            'Worked Hours', 'Target Hours', 'Diff Hours',
            'Gross Salary', 'Hourly Deduction', 'Absent Deduction',
            'Total Deduction', 'Overtime Pay',
            'Other Deductions', 'Reimbursements',
            'Net Salary',
        ])

        def fmt_hours(h):
            hrs = int(h)
            mins = int(round((h - hrs) * 60))
            return '%dh %02dm' % (hrs, mins)

        for line in report.line_ids.sorted(key=lambda l: l.employee_id.name):
            adj_absent_ded = line.absent_days_adj * (line.gross_salary / 30.0) if line.gross_salary else 0.0
            net = (line.gross_salary - line.total_deduction - adj_absent_ded
                   + line.overtime_pay - line.other_deductions + line.reimbursements)
            writer.writerow([
                line.employee_id.name,
                line.department_id.name or '',
                line.shift_count,
                line.days_worked,
                line.absent_days + line.absent_days_adj,
                line.flagged_count,
                fmt_hours(line.worked_hours),
                fmt_hours(line.target_hours),
                ('+' if line.diff_hours >= 0 else '') + fmt_hours(abs(line.diff_hours)),
                '%.2f' % line.gross_salary,
                '%.2f' % line.hourly_deduction,
                '%.2f' % line.absent_deduction,
                '%.2f' % line.total_deduction,
                '%.2f' % line.overtime_pay,
                '%.2f' % line.other_deductions,
                '%.2f' % line.reimbursements,
                '%.2f' % net,
            ])

        filename = 'Payroll_%s_%s.csv' % (
            report.date_from.strftime('%Y%m%d'),
            report.date_to.strftime('%Y%m%d'),
        )
        csv_content = output.getvalue().encode('utf-8-sig')

        return request.make_response(
            csv_content,
            headers=[
                ('Content-Type', 'text/csv;charset=utf-8'),
                ('Content-Disposition', content_disposition(filename)),
                ('Content-Length', len(csv_content)),
            ],
        )
