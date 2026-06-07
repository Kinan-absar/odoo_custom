# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, time, timedelta


class AttendanceSalaryReport(models.Model):
    _name = 'employee.attendance.salary.report'
    _description = 'Instant Attendance Salary Report'

    name = fields.Char(default='Instant Attendance Salary Report')
    date_from = fields.Date(string='From', required=True, default=lambda self: self._default_period()[0])
    date_to = fields.Date(string='To', required=True, default=lambda self: self._default_period()[1])
    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env.company)
    employee_ids = fields.Many2many('hr.employee', string='Employees',
                                    domain="[('company_id', '=', company_id)]")
    department_ids = fields.Many2many('hr.department', string='Departments',
                                    domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    work_location_ids = fields.Many2many('hr.work.location', string='Work Locations')
    include_inactive = fields.Boolean(string='Include Archived Employees')
    line_ids = fields.One2many('employee.attendance.salary.report.line', 'report_id', string='Lines')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    total_employees = fields.Integer(compute='_compute_totals')
    total_gross_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_basic_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_allowances = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_attendance_deductions = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_other_deductions = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_reimbursements = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_overtime_amount = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_net_salary = fields.Monetary(compute='_compute_totals', currency_field='currency_id')

    # Store the payroll structure ID as a plain Integer — no comodel reference,
    # so Odoo never tries to resolve hr.payroll.structure during read/onchange.
    struct_id = fields.Integer(
        string='Salary Structure',
        default=0,
        copy=False,
        help='ID of the hr.payroll.structure to apply to all payslips in the batch.',
    )
    payroll_batch_id = fields.Char(string='Payroll Batch', readonly=True)
    state = fields.Selection([
        ('draft', 'Not Generated'),
        ('generated', 'Generated'),
        ('batch_created', 'Batch Created'),
    ], string='Status', default='draft', readonly=True, copy=False)
    generated_on = fields.Datetime(string='Last Generated On', readonly=True, copy=False)
    batch_created_on = fields.Datetime(string='Batch Created On', readonly=True, copy=False)
    batch_created = fields.Boolean(compute='_compute_batch_created', store=True)

    @api.model
    def _default_period(self):
        today = fields.Date.context_today(self)
        if today.day >= 26:
            start = today.replace(day=26)
            end = today.replace(year=today.year + 1, month=1, day=25) \
                if today.month == 12 else today.replace(month=today.month + 1, day=25)
        else:
            end = today.replace(day=25)
            start = today.replace(year=today.year - 1, month=12, day=26) \
                if today.month == 1 else today.replace(month=today.month - 1, day=26)
        return start, end

    @api.depends('state', 'payroll_batch_id')
    def _compute_batch_created(self):
        for r in self:
            r.batch_created = r.state == 'batch_created' or bool(r.payroll_batch_id)

    @api.depends(
        'line_ids.gross_salary', 'line_ids.basic_salary', 'line_ids.total_allowances',
        'line_ids.attendance_deduction', 'line_ids.other_deductions',
        'line_ids.reimbursements', 'line_ids.overtime_amount', 'line_ids.net_salary',
    )
    def _compute_totals(self):
        for report in self:
            report.total_employees = len(report.line_ids)
            report.total_gross_salary = sum(report.line_ids.mapped('gross_salary'))
            report.total_basic_salary = sum(report.line_ids.mapped('basic_salary'))
            report.total_allowances = sum(report.line_ids.mapped('total_allowances'))
            report.total_attendance_deductions = sum(report.line_ids.mapped('attendance_deduction'))
            report.total_other_deductions = sum(report.line_ids.mapped('other_deductions'))
            report.total_reimbursements = sum(report.line_ids.mapped('reimbursements'))
            report.total_overtime_amount = sum(report.line_ids.mapped('overtime_amount'))
            report.total_net_salary = sum(report.line_ids.mapped('net_salary'))

    def _get_work_location_groups(self):
        """Return salary lines grouped by work location for PDF report."""
        self.ensure_one()
        groups = []
        location_map = {}
        for line in self.line_ids.sorted(
            key=lambda l: ((l.work_location_id.name or '') if l.work_location_id else _('No Work Location'),
                           l.employee_id.name or '')
        ):
            location = line.work_location_id
            key = location.id if location else 0
            if key not in location_map:
                group = {
                    'name': location.name if location else _('No Work Location'),
                    'lines': self.env['employee.attendance.salary.report.line'],
                    'employee_count': 0,
                    'gross_salary': 0.0,
                    'deductions': 0.0,
                    'reimbursements': 0.0,
                    'net_salary': 0.0,
                }
                location_map[key] = group
                groups.append(group)
            group = location_map[key]
            group['lines'] |= line
            group['employee_count'] += 1
            group['gross_salary'] += line.gross_salary
            group['deductions'] += line.attendance_deduction + line.other_deductions
            group['reimbursements'] += line.reimbursements
            group['net_salary'] += line.net_salary
        return groups

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_generate(self):
        """Rebuild lines in place. Returns False → stays on same page."""
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The start date must be before the end date.'))
        self.line_ids.unlink()
        lines = [(0, 0, self._prepare_employee_line(emp)) for emp in self._get_employees()]
        self.write({
            'line_ids': lines,
            'state': 'batch_created' if self.payroll_batch_id else 'generated',
            'generated_on': fields.Datetime.now(),
            'name': _('Attendance Salary Report %s → %s') % (self.date_from, self.date_to),
        })
        return False

    def action_create_payroll_batch(self):
        self.ensure_one()
        if 'hr.payslip.run' not in self.env.registry or 'hr.payslip' not in self.env.registry:
            raise UserError(_('Payroll is not installed.'))
        if not self.line_ids:
            raise UserError(_('Generate the report before creating a payroll batch.'))
        PayslipRun = self.env['hr.payslip.run'].sudo()
        Payslip = self.env['hr.payslip'].sudo()
        batch = PayslipRun.create({
            'name': _('Attendance Payroll %s → %s') % (self.date_from, self.date_to),
            'date_start': self.date_from,
            'date_end': self.date_to,
        })
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
            if self.struct_id and 'struct_id' in Payslip._fields:
                vals['struct_id'] = self.struct_id
            slip = Payslip.create(vals)
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

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('employee_portal_suite.action_report_salary_summary').report_action(self)

    # ── Data gathering ────────────────────────────────────────────────────────

    def _get_employees(self):
        domain = [('company_id', '=', self.company_id.id)]
        if self.employee_ids:
            domain.append(('id', 'in', self.employee_ids.ids))
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.work_location_ids:
            domain.append(('work_location_id', 'in', self.work_location_ids.ids))
        if not self.include_inactive:
            domain.append(('active', '=', True))
        return self.env['hr.employee'].sudo().search(domain, order='name')

    def _prepare_employee_line(self, employee):
        end_dt = datetime.combine(self.date_to, time.max)

        contract = self._get_contract(employee)

        # ── Attendance source from contract work_entry_source ─────────────────
        # 'attendance' → employee clocks in/out → actual hours monitored
        # 'calendar'   → working schedule only  → full credit, no deductions
        use_attendance = False
        if contract and 'work_entry_source' in contract._fields:
            use_attendance = (contract.work_entry_source == 'attendance')

        # ── Working calendar ──────────────────────────────────────────────────
        calendar_obj = (
            contract.resource_calendar_id
            if contract and 'resource_calendar_id' in contract._fields and contract.resource_calendar_id
            else employee.resource_calendar_id
        )
        hours_per_day = (
            calendar_obj.hours_per_day
            if calendar_obj and 'hours_per_day' in calendar_obj._fields and calendar_obj.hours_per_day
            else 8.0
        )
        schedule_expected_days = self._expected_working_days(calendar_obj)
        schedule_expected_hours = schedule_expected_days * hours_per_day

        # ── Target hours: employee override takes priority over schedule ───────
        # eps_target_hours > 0 means the employee has a custom target set
        employee_target_override = float(getattr(employee, 'eps_target_hours', 0.0) or 0.0)
        if employee_target_override > 0.0:
            expected_hours = employee_target_override
            # Days are still from the schedule (used for daily rate deduction logic)
            expected_days = schedule_expected_days
        else:
            expected_hours = schedule_expected_hours
            expected_days = schedule_expected_days

        # ── Overtime flag from employee ───────────────────────────────────────
        overtime_enabled = bool(getattr(employee, 'eps_overtime_enabled', False))

        # ── Attendance records — only when source is 'attendance' ─────────────
        attendance_worked_hours = 0.0
        attendance_count = 0
        days_worked = 0.0
        if use_attendance:
            start_dt = datetime.combine(self.date_from, time.min)
            attendances = self.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_in', '<=', fields.Datetime.to_string(end_dt)),
                '|',
                ('check_out', '=', False),
                ('check_out', '>=', fields.Datetime.to_string(start_dt)),
            ])
            attendance_worked_hours = sum(attendances.mapped('worked_hours'))
            attendance_count = len(attendances)
            # Count distinct calendar days with check-in
            days_worked = len(set(
                att.check_in.date() for att in attendances if att.check_in
            ))

        # For calendar employees: credit full expected hours
        worked_hours = attendance_worked_hours if use_attendance else expected_hours

        approved_leave_days, unpaid_leave_days, public_holiday_days = self._leave_days(employee, calendar_obj, contract)

        gross_salary, basic_salary, housing, transport, other_allowances = \
            self._salary_components(employee, contract)

        return {
            'company_id': employee.company_id.id,
            'employee_id': employee.id,
            'department_id': employee.department_id.id if employee.department_id else False,
            'work_location_id': employee.work_location_id.id if employee.work_location_id else False,
            'contract_id': contract.id if contract else False,
            'calendar_id': calendar_obj.id if calendar_obj else False,
            'use_attendance': use_attendance,
            'overtime_enabled': overtime_enabled,
            'gross_salary': gross_salary,
            'basic_salary': basic_salary,
            'housing_allowance': housing,
            'transport_allowance': transport,
            'other_allowances': other_allowances,
            'expected_days': expected_days,
            'expected_hours': expected_hours,
            'attendance_worked_hours': attendance_worked_hours,
            'worked_hours': worked_hours,
            'days_worked': days_worked,
            'approved_leave_days': approved_leave_days,
            'unpaid_leave_days': unpaid_leave_days,
            'public_holiday_days': public_holiday_days,
            'attendance_count': attendance_count,
        }

    # ── Salary helpers ────────────────────────────────────────────────────────

    def _get_contract(self, employee):
        if 'hr.contract' not in self.env.registry:
            return False
        domain = [('employee_id', '=', employee.id)]
        Contract = self.env['hr.contract']
        if 'company_id' in Contract._fields:
            domain.append(('company_id', '=', self.company_id.id))
        if 'state' in Contract._fields:
            domain.append(('state', 'in', ['open', 'close']))
        return Contract.sudo().search(domain, order='date_start desc, id desc', limit=1)[:1]

    def _salary_components(self, employee, contract=False):
        """
        Gross  = wage (contract)
        Basic  = Gross - Housing - Transport - Other
        Saudi localisation field names confirmed from contract screenshots.
        """
        gross = float(getattr(contract, 'wage', 0.0) or 0.0) if contract else 0.0
        housing = float(getattr(contract, 'l10n_sa_housing_allowance', 0.0) or 0.0) if contract else 0.0
        transport = float(getattr(contract, 'l10n_sa_transportation_allowance', 0.0) or 0.0) if contract else 0.0
        other = float(getattr(contract, 'l10n_sa_other_allowances', 0.0) or 0.0) if contract else 0.0
        basic = gross - housing - transport - other
        # Fallback: no allowances found → 35% split
        if gross and basic == gross and not (housing or transport or other):
            basic = gross / 1.35
            other = gross - basic
        return (max(gross, 0.0), max(basic, 0.0), max(housing, 0.0), max(transport, 0.0), max(other, 0.0))

    def _expected_working_days(self, calendar_obj=False):
        days = 0.0
        current = self.date_from
        while current <= self.date_to:
            if self._is_working_day(current, calendar_obj):
                days += 1
            current += timedelta(days=1)
        return days

    def _is_working_day(self, date_value, calendar_obj=False):
        weekday = date_value.weekday()
        attendance_weekdays = set()
        if calendar_obj and 'attendance_ids' in calendar_obj._fields:
            for att in calendar_obj.attendance_ids:
                if hasattr(att, 'dayofweek'):
                    attendance_weekdays.add(int(att.dayofweek))
        if attendance_weekdays:
            return weekday in attendance_weekdays
        return weekday < 5

    def _is_public_holiday_work_entry_type(self, work_entry_type):
        if not work_entry_type:
            return False
        name = ((work_entry_type.name or '') if 'name' in work_entry_type._fields else '').strip().lower()
        code = ((getattr(work_entry_type, 'code', '') or '') if 'code' in work_entry_type._fields else '').strip().lower()
        return 'public holiday' in name or 'public_holiday' in code or code == 'public' or 'public' in code

    def _is_unpaid_work_entry_type(self, work_entry_type):
        if not work_entry_type:
            return False
        name = ((work_entry_type.name or '') if 'name' in work_entry_type._fields else '').strip().lower()
        code = ((getattr(work_entry_type, 'code', '') or '') if 'code' in work_entry_type._fields else '').strip().lower()
        return 'unpaid' in name or 'unpaid' in code

    def _dates_from_range(self, start_value, end_value, calendar_obj=False, only_working_days=True):
        if not start_value or not end_value:
            return set()
        start_date = fields.Date.to_date(start_value)
        end_date = fields.Date.to_date(end_value)
        if not start_date or not end_date:
            return set()
        start_date = max(start_date, self.date_from)
        end_date = min(end_date, self.date_to)
        dates = set()
        current = start_date
        while current <= end_date:
            if not only_working_days or self._is_working_day(current, calendar_obj):
                dates.add(current)
            current += timedelta(days=1)
        return dates

    def _public_holiday_dates_from_work_entries(self, employee):
        if 'hr.work.entry' not in self.env.registry:
            return set()
        WorkEntry = self.env['hr.work.entry'].sudo()
        required = {'employee_id', 'work_entry_type_id', 'date_start', 'date_stop'}
        if not required.issubset(set(WorkEntry._fields)):
            return set()
        start_dt = datetime.combine(self.date_from, time.min)
        end_dt = datetime.combine(self.date_to, time.max)
        entries = WorkEntry.search([
            ('employee_id', '=', employee.id),
            ('date_start', '<=', fields.Datetime.to_string(end_dt)),
            ('date_stop', '>=', fields.Datetime.to_string(start_dt)),
        ])
        dates = set()
        for entry in entries:
            if self._is_public_holiday_work_entry_type(entry.work_entry_type_id):
                dates |= self._dates_from_range(entry.date_start, entry.date_stop, False, only_working_days=False)
        return dates

    def _public_holiday_dates_from_calendar_leaves(self, employee, calendar_obj=False):
        if 'resource.calendar.leaves' not in self.env.registry:
            return set()
        Leaves = self.env['resource.calendar.leaves'].sudo()
        if 'date_from' not in Leaves._fields or 'date_to' not in Leaves._fields:
            return set()
        start_dt = datetime.combine(self.date_from, time.min)
        end_dt = datetime.combine(self.date_to, time.max)
        domain = [
            ('date_from', '<=', fields.Datetime.to_string(end_dt)),
            ('date_to', '>=', fields.Datetime.to_string(start_dt)),
        ]
        if 'company_id' in Leaves._fields:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]
        if 'calendar_id' in Leaves._fields and calendar_obj:
            domain += ['|', ('calendar_id', '=', False), ('calendar_id', '=', calendar_obj.id)]
        leaves = Leaves.search(domain)
        dates = set()
        for leave in leaves:
            # Calendar leaves can include many reasons. Only count the ones explicitly linked/named as public holidays.
            work_entry_type = False
            if 'work_entry_type_id' in leave._fields and leave.work_entry_type_id:
                work_entry_type = leave.work_entry_type_id
            leave_name = ((getattr(leave, 'name', '') or '') if 'name' in leave._fields else '').strip().lower()
            if self._is_public_holiday_work_entry_type(work_entry_type) or 'public holiday' in leave_name or 'public holidays' in leave_name:
                dates |= self._dates_from_range(leave.date_from, leave.date_to, calendar_obj, only_working_days=True)
        return dates

    def _leave_days(self, employee, calendar_obj=False, contract=False):
        approved = unpaid = public_holiday = 0.0
        public_holiday_dates = set()

        if 'hr.leave' in self.env.registry:
            start_dt = datetime.combine(self.date_from, time.min)
            end_dt = datetime.combine(self.date_to, time.max)
            leaves = self.env['hr.leave'].sudo().search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', fields.Datetime.to_string(end_dt)),
                ('date_to', '>=', fields.Datetime.to_string(start_dt)),
            ])
            for leave in leaves:
                days = getattr(leave, 'number_of_days', 0.0) or getattr(leave, 'number_of_days_display', 0.0) or 0.0
                leave_type = leave.holiday_status_id if 'holiday_status_id' in leave._fields else False
                work_entry_type = (
                    leave_type.work_entry_type_id
                    if leave_type and 'work_entry_type_id' in leave_type._fields and leave_type.work_entry_type_id
                    else False
                )
                if self._is_public_holiday_work_entry_type(work_entry_type):
                    public_holiday += days
                    continue
                approved += days
                if self._is_unpaid_work_entry_type(work_entry_type):
                    unpaid += days
                elif leave_type:
                    for fname in ('unpaid', 'is_unpaid', 'unpaid_leave'):
                        if fname in leave_type._fields and getattr(leave_type, fname):
                            unpaid += days
                            break

        # In Odoo Payroll, public holidays are often not hr.leave records. They are generated
        # as hr.work.entry records or stored as global resource.calendar.leaves.
        public_holiday_dates |= self._public_holiday_dates_from_work_entries(employee)
        public_holiday_dates |= self._public_holiday_dates_from_calendar_leaves(employee, calendar_obj)
        public_holiday += float(len(public_holiday_dates))

        return approved, unpaid, public_holiday


# ══════════════════════════════════════════════════════════════════════════════
class AttendanceSalaryReportLine(models.Model):
    _name = 'employee.attendance.salary.report.line'
    _description = 'Instant Attendance Salary Report Line'
    _order = 'employee_id'

    report_id = fields.Many2one('employee.attendance.salary.report', required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    currency_id = fields.Many2one(related='report_id.currency_id', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    work_location_id = fields.Many2one('hr.work.location', string='Work Location', readonly=True)
    contract_id = fields.Integer(string='Contract ID', readonly=True)
    calendar_id = fields.Many2one('resource.calendar', string='Working Schedule', readonly=True)

    # Sourced from contract work_entry_source
    use_attendance = fields.Boolean(string='Tracks Attendance', readonly=True)
    # Sourced from employee.eps_overtime_enabled
    overtime_enabled = fields.Boolean(string='OT Enabled', readonly=True)

    # ── Salary breakdown ──────────────────────────────────────────────────────
    gross_salary = fields.Monetary(string='Gross Salary', currency_field='currency_id', readonly=True)
    basic_salary = fields.Monetary(string='Basic Salary', currency_field='currency_id', readonly=True)
    housing_allowance = fields.Monetary(string='Housing', currency_field='currency_id', readonly=True)
    transport_allowance = fields.Monetary(string='Transport', currency_field='currency_id', readonly=True)
    other_allowances = fields.Monetary(string='Other Allow.', currency_field='currency_id', readonly=True)
    total_allowances = fields.Monetary(
        string='Total Allowances', currency_field='currency_id',
        compute='_compute_amounts', store=True,
    )

    # ── Attendance / time ─────────────────────────────────────────────────────
    expected_days = fields.Float(string='Expected Days', readonly=True)
    expected_hours = fields.Float(string='Target Hours', readonly=True)
    attendance_worked_hours = fields.Float(string='Clocked Hours', readonly=True)
    worked_hours = fields.Float(string='Worked Hours', readonly=True)
    # Number of distinct calendar days the employee checked in
    days_worked = fields.Float(string='Days Worked', readonly=True)
    final_worked_hours = fields.Float(string='Final Worked Hours', compute='_compute_amounts', store=True)

    # ── Leave ─────────────────────────────────────────────────────────────────
    approved_leave_days = fields.Float(string='Approved Leave', readonly=True)
    unpaid_leave_days = fields.Float(string='Unpaid Leave', readonly=True)
    public_holiday_days = fields.Float(string='Public Holiday', readonly=True)
    system_absent_days = fields.Float(string='System Absent Days', compute='_compute_amounts', store=True)
    manual_absent_days = fields.Float(string='Manual Absent Days')
    final_absent_days = fields.Float(string='Final Absent Days', compute='_compute_amounts', store=True)

    # ── Computed amounts ──────────────────────────────────────────────────────
    daily_rate = fields.Monetary(string='Daily Rate', currency_field='currency_id', compute='_compute_amounts', store=True)
    gross_hourly_rate = fields.Monetary(string='Gross Hourly Rate', currency_field='currency_id', compute='_compute_amounts', store=True)
    basic_hourly_rate = fields.Monetary(string='Basic Hourly Rate', currency_field='currency_id', compute='_compute_amounts', store=True)
    overtime_hourly_rate = fields.Monetary(string='OT Hourly Rate', currency_field='currency_id', compute='_compute_amounts', store=True)

    # Day-level deduction: absent full days × daily rate
    absence_deduction = fields.Monetary(string='Absence Deduction (Days)', currency_field='currency_id', compute='_compute_amounts', store=True)
    # Hour-level deduction: shortage hours on days the employee DID show up
    shortage_hours = fields.Float(string='Shortage Hours', compute='_compute_amounts', store=True)
    shortage_deduction = fields.Monetary(string='Shortage Deduction (Hours)', currency_field='currency_id', compute='_compute_amounts', store=True)
    # Combined
    attendance_deduction = fields.Monetary(string='Total Att. Deduction', currency_field='currency_id', compute='_compute_amounts', store=True)

    overtime_hours = fields.Float(string='Overtime Hours', compute='_compute_amounts', store=True)
    overtime_amount = fields.Monetary(string='OT Amount', currency_field='currency_id', compute='_compute_amounts', store=True)

    # ── Manual adjustments ────────────────────────────────────────────────────
    other_deductions = fields.Monetary(string='Other Deductions', currency_field='currency_id')
    reimbursements = fields.Monetary(string='Reimbursements', currency_field='currency_id')
    net_salary = fields.Monetary(string='Estimated Net', currency_field='currency_id', compute='_compute_amounts', store=True)
    attendance_count = fields.Integer(string='Check-ins', readonly=True)

    @api.depends(
        'gross_salary', 'basic_salary',
        'housing_allowance', 'transport_allowance', 'other_allowances',
        'expected_days', 'expected_hours', 'worked_hours', 'days_worked',
        'manual_absent_days', 'approved_leave_days', 'unpaid_leave_days', 'public_holiday_days',
        'other_deductions', 'reimbursements',
        'use_attendance', 'overtime_enabled',
    )
    def _compute_amounts(self):
        for line in self:
            line.total_allowances = line.housing_allowance + line.transport_allowance + line.other_allowances

            # ── Rates ─────────────────────────────────────────────────────────
            # Daily rate  = Gross / 30
            # Gross hourly = Gross / 240
            # Basic hourly = Basic / 240
            # OT rate      = gross_hr + 0.5 × basic_hr  (1.5× effective)
            daily_rate = (line.gross_salary / 30.0) if line.gross_salary else 0.0
            gross_hourly_rate = (line.gross_salary / 240.0) if line.gross_salary else 0.0
            basic_hourly_rate = (line.basic_salary / 240.0) if line.basic_salary else 0.0
            overtime_hourly_rate = gross_hourly_rate + (0.5 * basic_hourly_rate)

            line.daily_rate = daily_rate
            line.gross_hourly_rate = gross_hourly_rate
            line.basic_hourly_rate = basic_hourly_rate
            line.overtime_hourly_rate = overtime_hourly_rate

            # ── CALENDAR employees (work_entry_source = 'calendar') ───────────
            # Full expected hours credited. No automatic deductions.
            # Only manual_absent_days can trigger a day-deduction.
            if not line.use_attendance:
                line.final_worked_hours = line.expected_hours
                line.system_absent_days = 0.0
                line.final_absent_days = (line.manual_absent_days or 0.0) + (line.unpaid_leave_days or 0.0)
                line.shortage_hours = 0.0
                line.shortage_deduction = 0.0
                line.absence_deduction = line.final_absent_days * daily_rate
                line.attendance_deduction = line.absence_deduction
                line.overtime_hours = 0.0
                line.overtime_amount = 0.0
                line.net_salary = (
                    line.gross_salary
                    - line.attendance_deduction
                    - (line.other_deductions or 0.0)
                    + (line.reimbursements or 0.0)
                )
                continue

            # ── ATTENDANCE employees (work_entry_source = 'attendance') ───────
            #
            # Algorithm (ported from attendance_pro AdminReports.tsx):
            #
            # 1. Payable expected days  = expected_days - approved_leave_days
            # 2. theoretical_hours_per_day = expected_hours / expected_days
            #    (or 8 if expected_days = 0)
            #
            # 3. ABSENT DAYS (day-level):
            #    system_absent_days = payable_expected_days - days_worked
            #    (days_worked = distinct calendar days with at least one check-in)
            #    final_absent_days  = system_absent_days + manual_absent_days
            #    absence_deduction  = final_absent_days × daily_rate
            #
            # 4. SHORTAGE HOURS (hour-level, ONLY on days the employee showed up):
            #    expected_hours_for_days_worked = days_worked × theoretical_hours_per_day
            #    hourly_shortfall = max(0, expected_hours_for_days_worked - worked_hours)
            #    shortage_deduction = hourly_shortfall × gross_hourly_rate
            #
            # The two deductions are separate and do NOT overlap:
            # - Absent days → deducted by the day
            # - Short hours on attended days → deducted by the hour
            #
            # 5. OVERTIME (only if employee.eps_overtime_enabled = True):
            #    overtime_hours = max(0, worked_hours - payable_expected_hours)
            #    overtime_amount = overtime_hours × overtime_hourly_rate
            #
            # 6. NET = Gross - absence_deduction - shortage_deduction + OT - other_ded + reimb

            target_hours = line.expected_hours
            days_for_calc = line.expected_days if line.expected_days > 0 else 26.0
            theoretical_hours_per_day = target_hours / days_for_calc if days_for_calc else 8.0

            paid_leave_days = max((line.approved_leave_days or 0.0) - (line.unpaid_leave_days or 0.0), 0.0)
            public_days = line.public_holiday_days or 0.0
            unpaid_days = line.unpaid_leave_days or 0.0

            # Public holidays and paid leave reduce the target with no deduction.
            # Unpaid leave is removed from the target to avoid double counting, then added back
            # as final absent days so it is deducted exactly once.
            non_working_days = public_days + paid_leave_days + unpaid_days
            payable_expected_days = max(line.expected_days - non_working_days, 0.0)
            payable_expected_hours = max(
                target_hours - (non_working_days * theoretical_hours_per_day), 0.0
            )

            actual_worked_hours = line.worked_hours
            actual_days_worked = line.days_worked  # distinct check-in days

            # ── Step 3: Absent days ───────────────────────────────────────────
            system_absent_days = max(0.0, payable_expected_days - actual_days_worked)
            final_absent_days = system_absent_days + unpaid_days + (line.manual_absent_days or 0.0)
            absence_deduction = final_absent_days * daily_rate

            # ── Step 4: Shortage hours (only on attended days) ────────────────
            expected_hours_for_days_worked = actual_days_worked * theoretical_hours_per_day
            hourly_shortfall = max(0.0, expected_hours_for_days_worked - actual_worked_hours)
            shortage_deduction = hourly_shortfall * gross_hourly_rate if hourly_shortfall > 0.01 else 0.0

            # ── Step 5: Overtime (gated by employee flag) ─────────────────────
            overtime_hours = 0.0
            overtime_amount = 0.0
            if line.overtime_enabled:
                overtime_hours = max(0.0, actual_worked_hours - payable_expected_hours)
                if overtime_hours > 0.01:
                    overtime_amount = overtime_hours * overtime_hourly_rate

            line.final_worked_hours = actual_worked_hours
            line.system_absent_days = system_absent_days
            line.final_absent_days = final_absent_days
            line.shortage_hours = hourly_shortfall
            line.absence_deduction = absence_deduction
            line.shortage_deduction = shortage_deduction
            line.attendance_deduction = absence_deduction + shortage_deduction
            line.overtime_hours = overtime_hours
            line.overtime_amount = overtime_amount
            line.net_salary = (
                line.gross_salary
                - absence_deduction
                - shortage_deduction
                + overtime_amount
                - (line.other_deductions or 0.0)
                + (line.reimbursements or 0.0)
            )
