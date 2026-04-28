# -*- coding: utf-8 -*-

import calendar
import csv
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.http import request


class AttendancePayrollReport(models.Model):
    _name = 'attendance.payroll.report'
    _description = 'Attendance Payroll Report'

    name = fields.Char(default='Attendance Payroll Report')
    date_from = fields.Date(required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(required=True, default=lambda self: self._default_date_to())
    department_id = fields.Many2one('hr.department', string='Department')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    standard_hours = fields.Float(string='Default Standard Hours', default=240.0, required=True)
    exclude_fridays = fields.Boolean(default=True)
    exclude_public_holidays = fields.Boolean(default=True)
    line_ids = fields.One2many('attendance.payroll.report.line', 'report_id', string='Report Lines')

    total_employees = fields.Integer(compute='_compute_totals')
    total_gross = fields.Float(compute='_compute_totals')
    total_hours = fields.Float(compute='_compute_totals')
    total_deductions = fields.Float(compute='_compute_totals')
    total_overtime = fields.Float(compute='_compute_totals')
    total_net = fields.Float(compute='_compute_totals')
    mudad_warning = fields.Text(readonly=True)

    @api.model
    def _default_date_to(self):
        today = fields.Date.context_today(self)
        return date(today.year, today.month, 25)

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        year = today.year
        month = today.month - 1
        if month == 0:
            month = 12
            year -= 1
        return date(year, month, 26)

    @api.depends('line_ids.gross_salary', 'line_ids.total_hours', 'line_ids.total_deductions', 'line_ids.overtime_pay', 'line_ids.net_salary')
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.total_employees = len(lines)
            rec.total_gross = sum(lines.mapped('gross_salary'))
            rec.total_hours = sum(lines.mapped('total_hours'))
            rec.total_deductions = sum(lines.mapped('total_deductions'))
            rec.total_overtime = sum(lines.mapped('overtime_pay'))
            rec.total_net = sum(lines.mapped('net_salary'))

    def _get_employees(self):
        domain = [('active', '=', True)]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        return self.env['hr.employee'].search(domain, order='name')

    def _holiday_dates(self):
        if not self.exclude_public_holidays:
            return set()
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('date_from', '<=', datetime.combine(self.date_to, time.max)),
            ('date_to', '>=', datetime.combine(self.date_from, time.min)),
            ('resource_id', '=', False),
        ])
        dates = set()
        for leave in leaves:
            cur = fields.Datetime.context_timestamp(self, leave.date_from).date()
            end = fields.Datetime.context_timestamp(self, leave.date_to).date()
            while cur <= end:
                if self.date_from <= cur <= self.date_to:
                    dates.add(cur)
                cur += timedelta(days=1)
        return dates

    def _expected_days(self, holiday_dates):
        days = []
        cur = self.date_from
        while cur <= self.date_to:
            if self.exclude_fridays and cur.weekday() == 4:
                cur += timedelta(days=1)
                continue
            if cur in holiday_dates:
                cur += timedelta(days=1)
                continue
            days.append(cur)
            cur += timedelta(days=1)
        return days

    def action_generate(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before Date To.'))

        self.line_ids.unlink()
        employees = self._get_employees()
        holiday_dates = self._holiday_dates()
        expected_days = self._expected_days(holiday_dates)
        expected_days_count = len(expected_days)

        start_dt = datetime.combine(self.date_from, time.min)
        end_dt = datetime.combine(self.date_to, time.max)
        attendances = self.env['hr.attendance'].search([
            ('employee_id', 'in', employees.ids),
            ('check_in', '>=', fields.Datetime.to_string(start_dt)),
            ('check_in', '<=', fields.Datetime.to_string(end_dt)),
        ])

        stats = defaultdict(lambda: {'hours': 0.0, 'shifts': 0, 'flagged': 0, 'worked_days': set()})
        for att in attendances:
            emp_stats = stats[att.employee_id.id]
            check_in_local = fields.Datetime.context_timestamp(self, att.check_in)
            emp_stats['worked_days'].add(check_in_local.date())
            emp_stats['shifts'] += 1
            if att.check_out:
                check_out_local = fields.Datetime.context_timestamp(self, att.check_out)
                emp_stats['hours'] += max(0.0, (check_out_local - check_in_local).total_seconds() / 3600.0)
            elif att.worked_hours:
                emp_stats['hours'] += att.worked_hours

        lines = []
        for emp in employees:
            s = stats[emp.id]
            worked_days = len(s['worked_days'])
            if worked_days == 0 and expected_days_count > 0:
                absent_days = 30.0
            else:
                absent_days = max(0.0, expected_days_count - worked_days)

            gross = emp.eps_gross_salary or 0.0
            basic = emp.eps_basic_salary or (gross / 1.35 if gross else 0.0)
            target_hours = emp.eps_standard_monthly_hours or self.standard_hours or 240.0
            gross_hourly = gross / 240.0 if gross else 0.0
            basic_hourly = basic / 240.0 if basic else 0.0
            daily_rate = gross / 30.0 if gross else 0.0
            hour_diff = s['hours'] - target_hours

            days_for_calc = expected_days_count or 26.0
            theoretical_hours_per_day = target_hours / days_for_calc if days_for_calc else 0.0
            expected_hours_for_days_worked = worked_days * theoretical_hours_per_day
            hourly_shortfall = max(0.0, expected_hours_for_days_worked - s['hours'])

            deductions_enabled = not emp.eps_disable_deductions
            overtime_enabled = not emp.eps_disable_overtime
            hourly_deduction = hourly_shortfall * gross_hourly if hourly_shortfall > 0.01 and deductions_enabled else 0.0
            absent_deduction = absent_days * daily_rate if deductions_enabled else 0.0
            overtime_rate = gross_hourly + (0.5 * basic_hourly)
            overtime_pay = hour_diff * overtime_rate if hour_diff > 0.01 and overtime_enabled else 0.0
            total_deductions = hourly_deduction + absent_deduction + (emp.eps_fixed_deductions or 0.0)
            net = gross - total_deductions + overtime_pay

            lines.append((0, 0, {
                'employee_id': emp.id,
                'department_id': emp.department_id.id,
                'is_on_leave': emp.eps_is_on_leave,
                'standard_hours': target_hours,
                'expected_days': expected_days_count,
                'days_worked': worked_days,
                'absent_days': absent_days,
                'adjusted_absent_days': 0.0,
                'shift_count': s['shifts'],
                'total_hours': s['hours'],
                'hour_diff': hour_diff,
                'gross_salary': gross,
                'basic_salary': basic,
                'housing_allowance': emp.eps_housing_allowance or 0.0,
                'other_allowances': emp.eps_other_allowances or 0.0,
                'fixed_deductions': emp.eps_fixed_deductions or 0.0,
                'hourly_deduction': hourly_deduction,
                'absent_deduction': absent_deduction,
                'overtime_pay': overtime_pay,
                'other_deductions': 0.0,
                'reimbursements': 0.0,
                'total_deductions': total_deductions,
                'net_salary': net,
            }))
        self.write({'line_ids': lines, 'mudad_warning': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()
        return self.env.ref('employee_portal_suite.action_report_attendance_payroll').report_action(self)

    def _mudad_lines_and_warnings(self):
        lines, warnings = [], []
        for line in self.line_ids:
            emp = line.employee_id
            iqama = (emp.eps_iqama_number or '').strip()
            bank = (emp.eps_bank_code or '').strip()
            iban = (emp.eps_iban_number or '').strip().replace(' ', '')
            emp_warnings = []
            if not iqama.isdigit() or len(iqama) != 10:
                emp_warnings.append(_('invalid Iqama/National ID'))
            if len(bank) != 4:
                emp_warnings.append(_('invalid bank code'))
            if len(iban) != 24 or not iban.startswith('SA'):
                emp_warnings.append(_('invalid IBAN'))
            if emp_warnings:
                warnings.append('%s: %s' % (emp.name, ', '.join(emp_warnings)))
                continue
            other_allowances = line.other_allowances + line.reimbursements
            lines.append(','.join([
                iqama,
                bank,
                iban,
                '%.2f' % line.basic_salary,
                '%.2f' % line.housing_allowance,
                '%.2f' % other_allowances,
                '%.2f' % line.total_deductions,
                '%.2f' % line.net_salary,
            ]))
        return lines, warnings

    def action_export_mudad(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()
        lines, warnings = self._mudad_lines_and_warnings()
        if not lines:
            raise UserError(_('No valid employees to export. Fill Iqama, Bank Code, IBAN, and salary breakdown first.'))
        self.mudad_warning = '\n'.join(warnings) if warnings else False
        return {
            'type': 'ir.actions.act_url',
            'url': '/attendance/payroll/mudad/%s' % self.id,
            'target': 'self',
        }

    def action_export_csv(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate()
        return {
            'type': 'ir.actions.act_url',
            'url': '/attendance/payroll/csv/%s' % self.id,
            'target': 'self',
        }


class AttendancePayrollReportLine(models.Model):
    _name = 'attendance.payroll.report.line'
    _description = 'Attendance Payroll Report Line'

    report_id = fields.Many2one('attendance.payroll.report', required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', required=True)
    department_id = fields.Many2one('hr.department')
    is_on_leave = fields.Boolean(string='On Leave')
    standard_hours = fields.Float()
    expected_days = fields.Float()
    days_worked = fields.Float()
    absent_days = fields.Float()
    adjusted_absent_days = fields.Float(string='Absent Days Adj')
    total_absent_days = fields.Float(compute='_compute_amounts', store=True)
    shift_count = fields.Integer()
    total_hours = fields.Float()
    hour_diff = fields.Float()
    gross_salary = fields.Float()
    basic_salary = fields.Float()
    housing_allowance = fields.Float()
    other_allowances = fields.Float()
    fixed_deductions = fields.Float()
    hourly_deduction = fields.Float(compute='_compute_amounts', store=True)
    absent_deduction = fields.Float(compute='_compute_amounts', store=True)
    overtime_pay = fields.Float(compute='_compute_amounts', store=True)
    other_deductions = fields.Float(string='Other Deductions')
    reimbursements = fields.Float()
    total_deductions = fields.Float(compute='_compute_amounts', store=True)
    net_salary = fields.Float(compute='_compute_amounts', store=True)

    @api.depends('employee_id.eps_disable_deductions', 'employee_id.eps_disable_overtime', 'standard_hours', 'expected_days', 'days_worked', 'absent_days', 'adjusted_absent_days', 'total_hours', 'gross_salary', 'basic_salary', 'fixed_deductions', 'other_deductions', 'reimbursements')
    def _compute_amounts(self):
        for line in self:
            gross_hourly = line.gross_salary / 240.0 if line.gross_salary else 0.0
            basic_hourly = line.basic_salary / 240.0 if line.basic_salary else 0.0
            daily_rate = line.gross_salary / 30.0 if line.gross_salary else 0.0
            line.total_absent_days = max(0.0, (line.absent_days or 0.0) + (line.adjusted_absent_days or 0.0))
            days_for_calc = line.expected_days or 26.0
            expected_hours_worked = (line.days_worked or 0.0) * ((line.standard_hours or 240.0) / days_for_calc)
            hourly_shortfall = max(0.0, expected_hours_worked - (line.total_hours or 0.0))
            deductions_enabled = not line.employee_id.eps_disable_deductions
            overtime_enabled = not line.employee_id.eps_disable_overtime
            line.hourly_deduction = hourly_shortfall * gross_hourly if hourly_shortfall > 0.01 and deductions_enabled else 0.0
            line.absent_deduction = line.total_absent_days * daily_rate if deductions_enabled else 0.0
            hour_diff = (line.total_hours or 0.0) - (line.standard_hours or 240.0)
            line.hour_diff = hour_diff
            line.overtime_pay = hour_diff * (gross_hourly + (0.5 * basic_hourly)) if hour_diff > 0.01 and overtime_enabled else 0.0
            line.total_deductions = line.hourly_deduction + line.absent_deduction + (line.fixed_deductions or 0.0) + (line.other_deductions or 0.0)
            line.net_salary = (line.gross_salary or 0.0) - line.total_deductions + line.overtime_pay + (line.reimbursements or 0.0)
