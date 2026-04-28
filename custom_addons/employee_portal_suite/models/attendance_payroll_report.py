from odoo import models, fields, api
from datetime import date, timedelta
import calendar


class AttendancePayrollReport(models.TransientModel):
    """
    Payroll Oversight Report — wizard + computed lines.
    Mirrors the AdminReports logic from the Smart Check-In app.
    """
    _name = 'attendance.payroll.report'
    _description = 'Attendance Payroll Report'

    # ── Filters ────────────────────────────────────────────────────────────────
    date_from = fields.Date(string='From', required=True,
                            default=lambda self: date.today().replace(day=1))
    date_to = fields.Date(string='To', required=True,
                          default=lambda self: date.today())
    employee_ids = fields.Many2many('hr.employee', string='Employees',
                                    help='Leave empty to include all employees')
    department_ids = fields.Many2many('hr.department', string='Departments')

    # ── Global payroll settings ────────────────────────────────────────────────
    standard_hours = fields.Float(string='Standard Hours / Month', default=240.0,
                                  help='Target hours per employee per month if no individual target is set')

    # ── Computed report lines (one per employee) ───────────────────────────────
    line_ids = fields.One2many('attendance.payroll.report.line', 'report_id',
                               string='Report Lines', readonly=True)

    # ── Summary totals (computed after generate) ───────────────────────────────
    total_gross = fields.Float(string='Total Gross', readonly=True, digits=(16, 2))
    total_deduction = fields.Float(string='Total Deductions', readonly=True, digits=(16, 2))
    total_overtime = fields.Float(string='Total Overtime', readonly=True, digits=(16, 2))
    total_net = fields.Float(string='Total Net', readonly=True, digits=(16, 2))
    total_hours = fields.Float(string='Total Hours Worked', readonly=True, digits=(16, 2))

    # ──────────────────────────────────────────────────────────────────────────
    # GENERATE
    # ──────────────────────────────────────────────────────────────────────────
    def action_generate(self):
        self.ensure_one()

        # 1. Delete old lines
        self.line_ids.unlink()

        date_from = self.date_from
        date_to = self.date_to

        # 2. Collect employees
        domain = []
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        employees = self.env['hr.employee'].search(domain)

        # 3. Get all attendance records in range (one query)
        attendances = self.env['hr.attendance'].search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', fields.Datetime.to_string(
                fields.Datetime.from_string(str(date_from) + ' 00:00:00'))),
            ('check_in', '<=', fields.Datetime.to_string(
                fields.Datetime.from_string(str(date_to) + ' 23:59:59'))),
        ])

        # 4. Get public holidays in range
        holiday_dates = set()
        if 'resource.calendar.leaves' in self.env:
            leaves = self.env['resource.calendar.leaves'].search([
                ('resource_id', '=', False),     # global / company holidays
                ('date_from', '<=', str(date_to) + ' 23:59:59'),
                ('date_to', '>=', str(date_from) + ' 00:00:00'),
            ])
            for leave in leaves:
                d = leave.date_from.date()
                while d <= leave.date_to.date():
                    if date_from <= d <= date_to:
                        holiday_dates.add(d)
                    d += timedelta(days=1)

        # 5. Count working days in range (Mon-Fri or Sun-Thu, excl. holidays)
        # Use Sat+Sun as weekend unless the company uses Sun-Thu schedule
        def is_working_day(d):
            return d.weekday() < 5 and d not in holiday_dates  # Mon=0 … Fri=4

        total_working_days = sum(
            1 for i in range((date_to - date_from).days + 1)
            if is_working_day(date_from + timedelta(days=i))
        )

        # 6. Build per-employee attendance map
        att_map = {}   # employee_id -> list of attendances
        for att in attendances:
            att_map.setdefault(att.employee_id.id, []).append(att)

        lines = []
        grand_gross = grand_ded = grand_ot = grand_net = grand_hours = 0.0

        for emp in employees.sorted(key=lambda e: e.name):
            emp_atts = att_map.get(emp.id, [])

            # Hours worked
            worked_hours = sum(a.worked_hours for a in emp_atts)

            # Days worked (unique calendar days with at least one check-in)
            days_worked = len({a.check_in.date() for a in emp_atts})

            # Absent days = working days in range that have NO attendance
            absent_days = max(0, total_working_days - days_worked)

            # Shifts (total sessions)
            shift_count = len(emp_atts)

            # Flagged records (e.g., very short shifts < 30 min)
            flagged_count = sum(1 for a in emp_atts if a.worked_hours < 0.5 and a.check_out)

            # ── Salary data from hr.employee fields (if available) ──────────
            gross_salary = getattr(emp, 'wage', 0.0) or 0.0
            # Fallback: check contract
            if not gross_salary:
                contract = self.env['hr.contract'].search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'open'),
                ], limit=1)
                if contract:
                    gross_salary = contract.wage or 0.0

            target_hours = self.standard_hours

            # ── Payroll computation (same logic as the app) ──────────────────
            gross_hourly_rate = gross_salary / 240.0 if gross_salary else 0.0
            basic_salary = gross_salary / 1.35 if gross_salary else 0.0
            basic_hourly_rate = basic_salary / 240.0
            overtime_hourly_rate = gross_hourly_rate + (0.5 * basic_hourly_rate)
            daily_rate = gross_salary / 30.0

            diff = worked_hours - target_hours

            # Hourly shortfall: only for days actually worked (same app logic)
            days_for_calc = total_working_days if total_working_days > 0 else 26
            theoretical_hours_per_day = target_hours / days_for_calc
            expected_hours_for_days_worked = days_worked * theoretical_hours_per_day
            hourly_shortfall = max(0.0, expected_hours_for_days_worked - worked_hours)

            hourly_deduction = hourly_shortfall * gross_hourly_rate
            absent_deduction = absent_days * daily_rate
            total_deduction = hourly_deduction + absent_deduction

            overtime_pay = (diff * overtime_hourly_rate) if diff > 0.01 else 0.0
            net_salary = gross_salary - total_deduction + overtime_pay

            grand_gross += gross_salary
            grand_ded += total_deduction
            grand_ot += overtime_pay
            grand_net += net_salary
            grand_hours += worked_hours

            lines.append({
                'report_id': self.id,
                'employee_id': emp.id,
                'department_id': emp.department_id.id,
                'worked_hours': worked_hours,
                'shift_count': shift_count,
                'days_worked': days_worked,
                'absent_days': absent_days,
                'flagged_count': flagged_count,
                'target_hours': target_hours,
                'diff_hours': diff,
                'gross_salary': gross_salary,
                'hourly_deduction': hourly_deduction,
                'absent_deduction': absent_deduction,
                'total_deduction': total_deduction,
                'overtime_pay': overtime_pay,
                'net_salary': net_salary,
            })

        if lines:
            self.env['attendance.payroll.report.line'].create(lines)

        self.write({
            'total_gross': grand_gross,
            'total_deduction': grand_ded,
            'total_overtime': grand_ot,
            'total_net': grand_net,
            'total_hours': grand_hours,
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'attendance.payroll.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_report(self):
        """Open the printable QWeb PDF report."""
        self.ensure_one()
        return self.env.ref(
            'employee_portal_suite.action_report_attendance_payroll'
        ).report_action(self)

    def action_export_csv(self):
        """Return CSV download URL via a controller."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/attendance/payroll/export/csv/%d' % self.id,
            'target': 'new',
        }


class AttendancePayrollReportLine(models.TransientModel):
    """One row per employee in the payroll report."""
    _name = 'attendance.payroll.report.line'
    _description = 'Attendance Payroll Report Line'
    _order = 'employee_id'

    report_id = fields.Many2one('attendance.payroll.report', ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)

    worked_hours = fields.Float('Worked Hours', readonly=True, digits=(16, 2))
    shift_count = fields.Integer('Shifts', readonly=True)
    days_worked = fields.Integer('Days Worked', readonly=True)
    absent_days = fields.Float('Absent Days', readonly=True, digits=(16, 1))
    flagged_count = fields.Integer('Flagged', readonly=True)
    target_hours = fields.Float('Target Hours', readonly=True, digits=(16, 2))
    diff_hours = fields.Float('Diff Hours', readonly=True, digits=(16, 2))

    gross_salary = fields.Float('Gross Salary', readonly=True, digits=(16, 2))
    hourly_deduction = fields.Float('Hourly Deduction', readonly=True, digits=(16, 2))
    absent_deduction = fields.Float('Absent Deduction', readonly=True, digits=(16, 2))
    total_deduction = fields.Float('Total Deduction', readonly=True, digits=(16, 2))
    overtime_pay = fields.Float('Overtime Pay', readonly=True, digits=(16, 2))

    # Editable adjustments
    other_deductions = fields.Float('Other Deductions', digits=(16, 2), default=0.0)
    reimbursements = fields.Float('Reimbursements', digits=(16, 2), default=0.0)
    absent_days_adj = fields.Float('Absent Adj.', digits=(16, 1), default=0.0,
                                   help='Manual absent day adjustment (positive = more absent)')

    net_salary = fields.Float('Net Salary', readonly=True, digits=(16, 2))

    @api.depends('gross_salary', 'total_deduction', 'overtime_pay',
                 'other_deductions', 'reimbursements', 'absent_days_adj')
    def _compute_net(self):
        for line in self:
            adj_absent_ded = line.absent_days_adj * (line.gross_salary / 30.0) if line.gross_salary else 0.0
            line.net_salary = (
                line.gross_salary
                - line.total_deduction
                - adj_absent_ded
                + line.overtime_pay
                - line.other_deductions
                + line.reimbursements
            )

    def _inverse_net(self):
        pass
