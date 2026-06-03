from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)

GLOBAL_DEFAULT_HOURS = 240.0
GLOBAL_DEFAULT_WORKING_DAYS = 26


def _period_bounds(year: int, month: int):
    end = date(year, month, 25)
    if month == 1:
        start = date(year - 1, 12, 26)
    else:
        start = date(year, month - 1, 26)
    return start, end


def _current_period():
    today = date.today()
    if today.day > 25:
        end_month = today.month + 1
        end_year = today.year
        if end_month == 13:
            end_month = 1
            end_year += 1
        return _period_bounds(end_year, end_month)
    return _period_bounds(today.year, today.month)


def _working_days_in_period(start: date, end: date, public_holidays=None):
    public_holidays = set(public_holidays or [])
    count = 0
    current = start
    while current <= end:
        # Saudi weekend: Friday + Saturday
        if current.weekday() not in (4, 5) and current not in public_holidays:
            count += 1
        current += timedelta(days=1)
    return count


class HrPayrollInstantAdjustment(models.Model):
    _name = 'hr.payroll.instant.adjustment'
    _description = 'Instant Payroll Report Adjustment'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, ondelete='cascade', index=True)
    period_start = fields.Date(string='Period Start (26th)', required=True)
    period_end = fields.Date(string='Period End (25th)', required=True)
    other_deductions = fields.Float(string='Other Deductions (SAR)', default=0.0)
    reimbursements = fields.Float(string='Reimbursements (SAR)', default=0.0)
    absent_days_adjustment = fields.Float(string='Absent Days Adjustment', default=0.0)
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_employee_period', 'UNIQUE(employee_id, period_start, period_end)',
         'An adjustment record already exists for this employee and period.')
    ]


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    instant_gross_salary = fields.Float(string='Gross Salary (SAR)')
    instant_basic_salary = fields.Float(string='Basic Salary Component (SAR)')
    instant_housing_allowance = fields.Float(string='Housing Allowance (SAR)')
    instant_other_allowances = fields.Float(string='Other Allowances (SAR)')
    instant_fixed_deductions = fields.Float(string='Fixed Monthly Deductions (SAR)')
    instant_standard_hours = fields.Float(string='Standard Monthly Hours', default=0)
    instant_disable_overtime = fields.Boolean(string='Disable Overtime Pay', default=False)
    instant_disable_deductions = fields.Boolean(string='Disable Hour/Day Deductions', default=False)
    iqama_number = fields.Char(string='Iqama / National ID')
    bank_code = fields.Char(string='Bank Code')
    iban_number = fields.Char(string='IBAN')

    def _get_effective_gross_salary(self):
        self.ensure_one()
        if self.instant_gross_salary:
            return self.instant_gross_salary
        if 'hr.contract' in self.env:
            contract = self.env['hr.contract'].sudo().search([
                ('employee_id', '=', self.id),
                ('state', '=', 'open'),
            ], limit=1)
            if contract:
                return contract.wage or 0.0
        return 0.0


class HrPayrollInstantReport(models.TransientModel):
    _name = 'hr.payroll.instant.report'
    _description = 'Instant Attendance Salary Report'

    name = fields.Char(default='Instant Attendance Salary Report')
    date_start = fields.Date(string='Start Date', required=True, default=lambda self: _current_period()[0])
    date_end = fields.Date(string='End Date', required=True, default=lambda self: _current_period()[1])
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    department_id = fields.Many2one('hr.department', string='Department')
    work_location_id = fields.Many2one('hr.work.location', string='Work Location')
    standard_hours = fields.Float(string='Standard Monthly Hours', default=GLOBAL_DEFAULT_HOURS)
    line_ids = fields.One2many('hr.payroll.instant.report.line', 'report_id', string='Lines')

    employee_count = fields.Integer(string='Employees', compute='_compute_totals')
    total_worked_hours = fields.Float(string='Total Worked Hours', compute='_compute_totals')
    total_expected_days = fields.Float(string='Total Expected Days', compute='_compute_totals')
    total_absent_days = fields.Float(string='Total Absent Days', compute='_compute_totals')
    total_overtime_hours = fields.Float(string='Total Overtime Hours', compute='_compute_totals')
    total_net_payable = fields.Float(string='Total Net Payable', compute='_compute_totals')

    @api.depends('line_ids.worked_hours', 'line_ids.expected_working_days', 'line_ids.total_absent_days', 'line_ids.overtime_hours', 'line_ids.net')
    def _compute_totals(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids)
            rec.total_worked_hours = sum(rec.line_ids.mapped('worked_hours'))
            rec.total_expected_days = sum(rec.line_ids.mapped('expected_working_days'))
            rec.total_absent_days = sum(rec.line_ids.mapped('total_absent_days'))
            rec.total_overtime_hours = sum(rec.line_ids.mapped('overtime_hours'))
            rec.total_net_payable = sum(rec.line_ids.mapped('net'))

    def _get_employees(self):
        self.ensure_one()
        domain = [('active', '=', True)]
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.work_location_id:
            domain.append(('work_location_id', '=', self.work_location_id.id))
        return self.env['hr.employee'].sudo().search(domain, order='name')

    def action_generate(self):
        self.ensure_one()
        if self.date_start > self.date_end:
            raise UserError(_('Start Date cannot be after End Date.'))

        holiday_dates = []
        if 'hr.leave.public.holiday.line' in self.env:
            ph_lines = self.env['hr.leave.public.holiday.line'].sudo().search([
                ('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
            ])
            holiday_dates = [fields.Date.to_date(l.date) for l in ph_lines]

        expected_working_days = _working_days_in_period(self.date_start, self.date_end, holiday_dates)
        global_hours = self.standard_hours or GLOBAL_DEFAULT_HOURS

        self.line_ids.unlink()
        lines = []
        for emp in self._get_employees():
            lines.append((0, 0, self._compute_employee_line(emp, expected_working_days, global_hours)))
        self.write({'line_ids': lines})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Instant Attendance Salary Report'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_payroll_batch(self):
        self.ensure_one()
        if 'hr.payroll.run' not in self.env or 'hr.payslip' not in self.env:
            raise UserError(_('Payroll is not installed. Install Payroll first to create payroll batches.'))
        if not self.line_ids:
            self.action_generate()

        batch = self.env['hr.payroll.run'].sudo().create({
            'name': _('Instant Attendance Salary Report - %s to %s') % (self.date_start, self.date_end),
            'date_start': self.date_start,
            'date_end': self.date_end,
        })
        created = 0
        for line in self.line_ids:
            contract = self.env['hr.contract'].sudo().search([
                ('employee_id', '=', line.employee_id.id),
                ('state', '=', 'open'),
            ], limit=1)
            if not contract:
                continue
            self.env['hr.payslip'].sudo().create({
                'name': _('Salary Slip - %s') % line.employee_id.name,
                'employee_id': line.employee_id.id,
                'contract_id': contract.id,
                'payslip_run_id': batch.id,
                'date_from': self.date_start,
                'date_to': self.date_end,
            })
            created += 1
        if not created:
            raise UserError(_('No payslips were created because no selected employee has an open contract.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payroll Batch'),
            'res_model': 'hr.payroll.run',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _compute_employee_line(self, emp, expected_working_days, global_hours):
        gross_salary = emp._get_effective_gross_salary()
        basic_salary = emp.instant_basic_salary or (gross_salary / 1.35 if gross_salary else 0.0)
        housing_allowance = emp.instant_housing_allowance or 0.0
        other_allowances = emp.instant_other_allowances or 0.0
        fixed_deductions = emp.instant_fixed_deductions or 0.0
        target_hours = emp.instant_standard_hours or global_hours
        ot_enabled = not emp.instant_disable_overtime
        ded_enabled = not emp.instant_disable_deductions

        daily_rate = gross_salary / 30.0 if gross_salary else 0.0
        gross_hourly_rate = gross_salary / 240.0 if gross_salary else 0.0
        basic_hourly_rate = basic_salary / 240.0 if basic_salary else 0.0
        overtime_hourly_rate = gross_hourly_rate + 0.5 * basic_hourly_rate

        start_dt = datetime.combine(self.date_start, datetime.min.time())
        end_dt = datetime.combine(self.date_end, datetime.max.time())
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', emp.id),
            ('check_in', '>=', fields.Datetime.to_string(start_dt)),
            ('check_in', '<=', fields.Datetime.to_string(end_dt)),
        ])
        worked_hours = sum(a.worked_hours or 0.0 for a in attendances)

        days_worked_set = set()
        for att in attendances:
            if att.check_in:
                tz_name = emp.tz or self.env.user.tz or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except Exception:
                    tz = pytz.utc
                check_in = att.check_in
                if check_in.tzinfo is None:
                    local_dt = pytz.utc.localize(check_in).astimezone(tz)
                else:
                    local_dt = check_in.astimezone(tz)
                days_worked_set.add(local_dt.date())
        days_worked = len(days_worked_set)

        approved_leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', emp.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Datetime.to_string(end_dt)),
            ('date_to', '>=', fields.Datetime.to_string(start_dt)),
        ])
        absent_days_from_leave = 0.0
        for leave in approved_leaves:
            leave_start = max(fields.Date.to_date(leave.date_from), self.date_start)
            leave_end = min(fields.Date.to_date(leave.date_to), self.date_end)
            d = leave_start
            while d <= leave_end:
                if d.weekday() not in (4, 5):
                    absent_days_from_leave += 1
                d += timedelta(days=1)

        adj = self.env['hr.payroll.instant.adjustment'].sudo().search([
            ('employee_id', '=', emp.id),
            ('period_start', '=', self.date_start),
            ('period_end', '=', self.date_end),
        ], limit=1)
        adj_other_ded = adj.other_deductions if adj else 0.0
        adj_reimbursements = adj.reimbursements if adj else 0.0
        adj_absent_days = adj.absent_days_adjustment if adj else 0.0
        total_absent_days = absent_days_from_leave + adj_absent_days

        days_for_calc = expected_working_days if expected_working_days > 0 else GLOBAL_DEFAULT_WORKING_DAYS
        theoretical_hours_per_day = target_hours / days_for_calc
        expected_hours_for_days_worked = days_worked * theoretical_hours_per_day
        hourly_shortfall = max(0.0, expected_hours_for_days_worked - worked_hours)
        hourly_deduction = (hourly_shortfall * gross_hourly_rate) if hourly_shortfall > 0.01 and ded_enabled else 0.0
        absent_deduction = (total_absent_days * daily_rate) if ded_enabled else 0.0
        total_deduction = hourly_deduction + absent_deduction
        diff = worked_hours - target_hours
        overtime_hours = max(0.0, diff)
        overtime_pay = (overtime_hours * overtime_hourly_rate) if overtime_hours > 0.01 and ot_enabled else 0.0
        other_ded_total = adj_other_ded + fixed_deductions
        net_salary = gross_salary - total_deduction + overtime_pay - other_ded_total + adj_reimbursements

        leave_balance = 0.0
        leave_taken_ytd = 0.0
        leave_allocation_total = 0.0
        if 'hr.leave.allocation' in self.env:
            today = date.today()
            allocations = self.env['hr.leave.allocation'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'validate'),
            ])
            leave_allocation_total = sum(alloc.number_of_days or 0.0 for alloc in allocations)
            taken_leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'validate'),
                ('date_from', '>=', f'{today.year}-01-01 00:00:00'),
                ('date_to', '<=', f'{today.year}-12-31 23:59:59'),
            ])
            leave_taken_ytd = sum(l.number_of_days or 0.0 for l in taken_leaves)
            leave_balance = leave_allocation_total - leave_taken_ytd

        return {
            'employee_id': emp.id,
            'department_id': emp.department_id.id,
            'job_id': emp.job_id.id,
            'worked_hours': round(worked_hours, 2),
            'shift_count': len(attendances),
            'days_worked': days_worked,
            'expected_working_days': expected_working_days,
            'target_hours': round(target_hours, 2),
            'hourly_shortfall': round(hourly_shortfall, 2),
            'overtime_hours': round(overtime_hours, 2),
            'absent_days_from_leave': round(absent_days_from_leave, 2),
            'adj_absent_days': round(adj_absent_days, 2),
            'total_absent_days': round(total_absent_days, 2),
            'gross': round(gross_salary, 2),
            'basic_salary': round(basic_salary, 2),
            'housing_allowance': round(housing_allowance, 2),
            'other_allowances': round(other_allowances, 2),
            'fixed_deductions': round(fixed_deductions, 2),
            'hourly_deduction': round(hourly_deduction, 2),
            'absent_deduction': round(absent_deduction, 2),
            'deduction': round(total_deduction, 2),
            'other_ded': round(other_ded_total, 2),
            'overtime': round(overtime_pay, 2),
            'reimb': round(adj_reimbursements, 2),
            'net': round(net_salary, 2),
            'leave_allocation_total': round(leave_allocation_total, 2),
            'leave_taken_ytd': round(leave_taken_ytd, 2),
            'leave_balance': round(leave_balance, 2),
        }


class HrPayrollInstantReportLine(models.TransientModel):
    _name = 'hr.payroll.instant.report.line'
    _description = 'Instant Attendance Salary Report Line'

    report_id = fields.Many2one('hr.payroll.instant.report', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    shift_count = fields.Integer(string='Shifts', readonly=True)
    days_worked = fields.Float(string='Worked Days', readonly=True)
    expected_working_days = fields.Float(string='Expected Days', readonly=True)
    target_hours = fields.Float(string='Target Hours', readonly=True)
    hourly_shortfall = fields.Float(string='Shortage Hours', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    absent_days_from_leave = fields.Float(string='Approved Leave Days', readonly=True)
    adj_absent_days = fields.Float(string='Manual Absent Days', readonly=True)
    total_absent_days = fields.Float(string='Absent Days', readonly=True)
    gross = fields.Float(string='Gross Salary', readonly=True)
    basic_salary = fields.Float(string='Basic Salary', readonly=True)
    housing_allowance = fields.Float(string='Housing Allowance', readonly=True)
    other_allowances = fields.Float(string='Other Allowances', readonly=True)
    fixed_deductions = fields.Float(string='Fixed Deductions', readonly=True)
    hourly_deduction = fields.Float(string='Hourly Deduction', readonly=True)
    absent_deduction = fields.Float(string='Absent Deduction', readonly=True)
    deduction = fields.Float(string='Deductions', readonly=True)
    other_ded = fields.Float(string='Other Deductions', readonly=True)
    overtime = fields.Float(string='Overtime Pay', readonly=True)
    reimb = fields.Float(string='Reimbursements', readonly=True)
    net = fields.Float(string='Net Payable', readonly=True)
    leave_allocation_total = fields.Float(string='Annual Leave Allocation', readonly=True)
    leave_taken_ytd = fields.Float(string='Leave Taken YTD', readonly=True)
    leave_balance = fields.Float(string='Leave Balance', readonly=True)
