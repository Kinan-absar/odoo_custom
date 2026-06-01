# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import date, datetime, time, timedelta
import calendar


class AttendanceSalaryReport(models.Model):
    _name = 'employee.attendance.salary.report'
    _description = 'Instant Attendance Salary Report'

    name = fields.Char(default='Instant Attendance Salary Report')
    date_from = fields.Date(string='From', required=True, default=lambda self: self._default_period()[0])
    date_to = fields.Date(string='To', required=True, default=lambda self: self._default_period()[1])
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    department_id = fields.Many2one('hr.department', string='Department')
    include_inactive = fields.Boolean(string='Include Archived Employees')
    line_ids = fields.One2many('employee.attendance.salary.report.line', 'report_id', string='Lines', readonly=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    total_employees = fields.Integer(compute='_compute_totals')
    total_basic_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_gross_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_deductions = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_overtime_amount = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_net_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    payroll_batch_id = fields.Many2one('hr.payslip.run', string='Payroll Batch', readonly=True) if False else fields.Char(string='Payroll Batch', readonly=True)
    state = fields.Selection([
        ('draft', 'Not Generated'),
        ('generated', 'Generated - No Batch'),
        ('batch_created', 'Batch Created'),
    ], string='Status', default='draft', readonly=True, copy=False)
    generated_on = fields.Datetime(string='Last Generated On', readonly=True, copy=False)
    batch_created_on = fields.Datetime(string='Batch Created On', readonly=True, copy=False)
    batch_created = fields.Boolean(string='Payroll Batch Created', compute='_compute_batch_created', store=True)


    @api.model
    def _default_period(self):
        today = fields.Date.context_today(self)
        if today.day >= 26:
            start = today.replace(day=26)
            if today.month == 12:
                end = today.replace(year=today.year + 1, month=1, day=25)
            else:
                end = today.replace(month=today.month + 1, day=25)
        else:
            end = today.replace(day=25)
            if today.month == 1:
                start = today.replace(year=today.year - 1, month=12, day=26)
            else:
                start = today.replace(month=today.month - 1, day=26)
        return start, end

    @api.depends('state', 'payroll_batch_id')
    def _compute_batch_created(self):
        for report in self:
            report.batch_created = report.state == 'batch_created' or bool(report.payroll_batch_id)

    @api.depends('line_ids.basic_salary', 'line_ids.gross_salary', 'line_ids.absence_deduction', 'line_ids.shortage_deduction', 'line_ids.overtime_amount', 'line_ids.net_salary')
    def _compute_totals(self):
        for report in self:
            report.total_employees = len(report.line_ids)
            report.total_basic_salary = sum(report.line_ids.mapped('basic_salary'))
            report.total_gross_salary = sum(report.line_ids.mapped('gross_salary'))
            report.total_deductions = sum(report.line_ids.mapped('absence_deduction')) + sum(report.line_ids.mapped('shortage_deduction'))
            report.total_overtime_amount = sum(report.line_ids.mapped('overtime_amount'))
            report.total_net_salary = sum(report.line_ids.mapped('net_salary'))

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The start date must be before the end date.'))

        self.line_ids.unlink()
        employees = self._get_employees()
        line_vals = []
        for employee in employees:
            line_vals.append((0, 0, self._prepare_employee_line(employee)))
        self.write({
            'line_ids': line_vals,
            'state': 'batch_created' if self.payroll_batch_id else 'generated',
            'generated_on': fields.Datetime.now(),
            'name': _('Attendance Salary Report %s to %s') % (self.date_from, self.date_to),
        })
        # Return the same saved record in the same form. This avoids the odd
        # breadcrumb/new-record behavior caused by reload or opening a fresh action.
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
            'context': {'form_view_initial_mode': 'edit'},
        }

    def action_create_payroll_batch(self):
        self.ensure_one()
        if 'hr.payslip.run' not in self.env.registry or 'hr.payslip' not in self.env.registry:
            raise UserError(_('Payroll is not installed. Install Payroll first, then this report can create a payslip batch for the selected employees.'))
        if not self.line_ids:
            raise UserError(_('Generate the report before creating a payroll batch.'))

        PayslipRun = self.env['hr.payslip.run'].sudo()
        Payslip = self.env['hr.payslip'].sudo()
        batch = PayslipRun.create({
            'name': _('Attendance Payroll %s to %s') % (self.date_from, self.date_to),
            'date_start': self.date_from,
            'date_end': self.date_to,
        })
        created = 0
        for line in self.line_ids.filtered(lambda l: l.employee_id):
            vals = {
                'name': _('Salary Slip - %s - %s/%s') % (line.employee_id.name, self.date_from, self.date_to),
                'employee_id': line.employee_id.id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'payslip_run_id': batch.id,
            }
            if line.contract_id and 'contract_id' in Payslip._fields:
                vals['contract_id'] = line.contract_id
            slip = Payslip.create(vals)
            created += 1
            if hasattr(slip, 'compute_sheet'):
                slip.compute_sheet()
        self.write({
            'payroll_batch_id': batch.name,
            'state': 'batch_created',
            'batch_created_on': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'res_id': batch.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_employees(self):
        domain = []
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if not self.include_inactive:
            domain.append(('active', '=', True))
        return self.env['hr.employee'].sudo().search(domain, order='name')

    def _prepare_employee_line(self, employee):
        start_dt = datetime.combine(self.date_from, time.min)
        end_dt = datetime.combine(self.date_to, time.max)
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '<=', fields.Datetime.to_string(end_dt)),
            '|', ('check_out', '=', False), ('check_out', '>=', fields.Datetime.to_string(start_dt)),
        ])
        worked_hours = sum(attendances.mapped('worked_hours'))
        contract = self._get_contract(employee)
        basic_salary = contract.wage if contract and 'wage' in contract._fields else 0.0
        calendar_obj = contract.resource_calendar_id if contract and 'resource_calendar_id' in contract._fields and contract.resource_calendar_id else employee.resource_calendar_id
        hours_per_day = calendar_obj.hours_per_day if calendar_obj and 'hours_per_day' in calendar_obj._fields and calendar_obj.hours_per_day else 8.0
        expected_days = self._expected_working_days(calendar_obj)
        expected_hours = expected_days * hours_per_day
        approved_leave_days, unpaid_leave_days = self._leave_days(employee)
        payable_expected_days = max(expected_days - approved_leave_days, 0.0)
        payable_expected_hours = max(expected_hours - (approved_leave_days * hours_per_day), 0.0)
        shortage_hours = max(payable_expected_hours - worked_hours, 0.0)
        overtime_hours = max(worked_hours - payable_expected_hours, 0.0)
        absent_days = min(shortage_hours / hours_per_day if hours_per_day else 0.0, payable_expected_days)
        daily_rate = basic_salary / expected_days if expected_days else 0.0
        hourly_rate = daily_rate / hours_per_day if hours_per_day else 0.0
        shortage_deduction = shortage_hours * hourly_rate
        absence_deduction = absent_days * daily_rate
        overtime_amount = overtime_hours * hourly_rate
        net_salary = basic_salary - shortage_deduction + overtime_amount
        return {
            'employee_id': employee.id,
            'department_id': employee.department_id.id,
            'contract_id': contract.id if contract else False,
            'calendar_id': calendar_obj.id if calendar_obj else False,
            'basic_salary': basic_salary,
            'gross_salary': basic_salary,
            'expected_days': expected_days,
            'expected_hours': expected_hours,
            'worked_hours': worked_hours,
            'approved_leave_days': approved_leave_days,
            'unpaid_leave_days': unpaid_leave_days,
            'absent_days': absent_days,
            'shortage_hours': shortage_hours,
            'overtime_hours': overtime_hours,
            'daily_rate': daily_rate,
            'hourly_rate': hourly_rate,
            'absence_deduction': absence_deduction,
            'shortage_deduction': shortage_deduction,
            'overtime_amount': overtime_amount,
            'net_salary': net_salary,
            'attendance_count': len(attendances),
            'auto_checkout_count': len(attendances.filtered(lambda a: getattr(a, 'auto_checked_out', False))),
            'outside_location_count': len(attendances.filtered(lambda a: getattr(a, 'checkout_outside_location', False))),
        }

    def _get_contract(self, employee):
        if 'hr.contract' not in self.env.registry:
            return False
        domain = [('employee_id', '=', employee.id)]
        if 'state' in self.env['hr.contract']._fields:
            domain.append(('state', 'in', ['open', 'close']))
        contracts = self.env['hr.contract'].sudo().search(domain, order='date_start desc, id desc', limit=1)
        return contracts[:1]

    def _expected_working_days(self, calendar_obj=False):
        days = 0.0
        current = self.date_from
        attendance_weekdays = set()
        if calendar_obj and 'attendance_ids' in calendar_obj._fields:
            for att in calendar_obj.attendance_ids:
                if hasattr(att, 'dayofweek'):
                    attendance_weekdays.add(int(att.dayofweek))
        while current <= self.date_to:
            weekday = current.weekday()
            if attendance_weekdays:
                if weekday in attendance_weekdays:
                    days += 1
            elif weekday < 5:
                days += 1
            current += timedelta(days=1)
        return days

    def _leave_days(self, employee):
        if 'hr.leave' not in self.env.registry:
            return 0.0, 0.0
        start_dt = datetime.combine(self.date_from, time.min)
        end_dt = datetime.combine(self.date_to, time.max)
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Datetime.to_string(end_dt)),
            ('date_to', '>=', fields.Datetime.to_string(start_dt)),
        ])
        approved = 0.0
        unpaid = 0.0
        for leave in leaves:
            days = getattr(leave, 'number_of_days', 0.0) or getattr(leave, 'number_of_days_display', 0.0) or 0.0
            approved += days
            leave_type = leave.holiday_status_id if 'holiday_status_id' in leave._fields else False
            is_unpaid = False
            if leave_type:
                for field_name in ('unpaid', 'is_unpaid', 'unpaid_leave'):
                    if field_name in leave_type._fields and getattr(leave_type, field_name):
                        is_unpaid = True
            if is_unpaid:
                unpaid += days
        return approved, unpaid


class AttendanceSalaryReportLine(models.Model):
    _name = 'employee.attendance.salary.report.line'
    _description = 'Instant Attendance Salary Report Line'
    _order = 'employee_id'

    report_id = fields.Many2one('employee.attendance.salary.report', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='report_id.currency_id', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    contract_id = fields.Many2one('hr.contract', string='Contract', readonly=True) if False else fields.Integer(string='Contract ID', readonly=True)
    calendar_id = fields.Many2one('resource.calendar', string='Working Schedule', readonly=True)
    basic_salary = fields.Monetary(string='Basic Salary', currency_field='currency_id', readonly=True)
    gross_salary = fields.Monetary(string='Gross Salary', currency_field='currency_id', readonly=True)
    expected_days = fields.Float(string='Expected Days', readonly=True)
    expected_hours = fields.Float(string='Expected Hours', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    approved_leave_days = fields.Float(string='Approved Leave', readonly=True)
    unpaid_leave_days = fields.Float(string='Unpaid Leave', readonly=True)
    absent_days = fields.Float(string='Absence Days', readonly=True)
    shortage_hours = fields.Float(string='Shortage Hours', readonly=True)
    overtime_hours = fields.Float(string='Overtime Hours', readonly=True)
    daily_rate = fields.Monetary(string='Daily Rate', currency_field='currency_id', readonly=True)
    hourly_rate = fields.Monetary(string='Hourly Rate', currency_field='currency_id', readonly=True)
    absence_deduction = fields.Monetary(string='Absence Deduction', currency_field='currency_id', readonly=True)
    shortage_deduction = fields.Monetary(string='Shortage Deduction', currency_field='currency_id', readonly=True)
    overtime_amount = fields.Monetary(string='Overtime Amount', currency_field='currency_id', readonly=True)
    net_salary = fields.Monetary(string='Estimated Net', currency_field='currency_id', readonly=True)
    attendance_count = fields.Integer(string='Attendance Entries', readonly=True)
    auto_checkout_count = fields.Integer(string='Auto Checkouts', readonly=True)
    outside_location_count = fields.Integer(string='Outside Location', readonly=True)
