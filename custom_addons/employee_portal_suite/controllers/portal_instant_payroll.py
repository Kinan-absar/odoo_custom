"""
Instant Payroll Report Controller
==================================
Replicates the Attendance Pro "Instance Report" logic — live 26th-to-25th
payroll computation — using data already stored in Odoo:

  • hr.attendance        → worked hours, check-in/out records
  • hr.leave            → approved time-off (absence days)
  • hr.leave.allocation → annual allocation & remaining balance
  • hr.employee         → salary fields, WPS fields
  • hr.contract         → wage fallback
  • hr.payroll.instant.adjustment → manual adjustments per employee/period

Salary maths are identical to Attendance Pro's AdminReports.tsx:
  grossHourlyRate       = grossSalary / 240
  basicHourlyRate       = (grossSalary / 1.35) / 240
  overtimeHourlyRate    = grossHourlyRate + 0.5 * basicHourlyRate
  dailyRate             = grossSalary / 30
  hourlyShortfall       = max(0, expectedHoursForDaysWorked − workedHours)
  hourlyDeduction       = hourlyShortfall * grossHourlyRate   (if deductions enabled)
  absentDeduction       = absentDays * dailyRate              (if deductions enabled)
  overtimePay           = overtimeHours * overtimeHourlyRate  (if OT enabled)
  netSalary             = gross − totalDeduction + OT − otherDed + reimbursements
"""

from odoo import http, fields
from odoo.http import request
from datetime import date, datetime, timedelta
import pytz
import json
import logging

_logger = logging.getLogger(__name__)

# ── Payroll period helpers ───────────────────────────────────────────────────

GLOBAL_DEFAULT_HOURS = 240.0
GLOBAL_DEFAULT_WORKING_DAYS = 26


def _period_bounds(year: int, month: int):
    """
    Return (period_start, period_end) for the payroll cycle that *ends*
    on the 25th of the given year/month.

    The period always runs from the 26th of the *previous* month to the
    25th of the given month, exactly mirroring Attendance Pro.
    """
    end = date(year, month, 25)
    if month == 1:
        start = date(year - 1, 12, 26)
    else:
        start = date(year, month - 1, 26)
    return start, end


def _current_period():
    """Return the period that covers today."""
    today = date.today()
    # If today > 25 we are already in the next cycle (26 of this month → 25 next)
    if today.day > 25:
        return _period_bounds(
            today.year if today.month < 12 else today.year + 1,
            today.month % 12 + 1
        )
    return _period_bounds(today.year, today.month)


def _working_days_in_period(start: date, end: date, public_holidays=None):
    """
    Count Mon-Fri working days between start and end (inclusive).
    Subtracts any public holidays (list of date objects) that fall on weekdays.
    Saudi weekend = Fri+Sat, so we exclude Fri (4) and Sat (5).
    """
    public_holidays = set(public_holidays or [])
    count = 0
    current = start
    while current <= end:
        if current.weekday() not in (4, 5) and current not in public_holidays:
            count += 1
        current += timedelta(days=1)
    return count


# ── Main controller ──────────────────────────────────────────────────────────

class InstantPayrollReportController(http.Controller):

    # ------------------------------------------------------------------
    # ACCESS GUARD
    # ------------------------------------------------------------------
    def _require_hr_manager(self):
        """Raise if the current user is not an HR manager or system admin."""
        if not (
            request.env.user.has_group('hr.group_hr_manager') or
            request.env.user.has_group('base.group_system') or
            request.env.user.has_group('employee_portal_suite.group_employee_portal_hr')
        ):
            raise request.not_found()

    # ------------------------------------------------------------------
    # MAIN PAGE
    # ------------------------------------------------------------------
    @http.route('/odoo/instant-payroll', type='http', auth='user', website=True)
    def instant_payroll_report_page(self, year=None, month=None, **kw):
        self._require_hr_manager()

        today = date.today()
        try:
            year = int(year) if year else today.year
            month = int(month) if month else today.month
        except (TypeError, ValueError):
            year, month = today.year, today.month

        period_start, period_end = _period_bounds(year, month)

        # Build month navigation list (last 13 months)
        periods = []
        y, m = today.year, today.month
        for _ in range(13):
            ps, pe = _period_bounds(y, m)
            periods.append({
                'year': y,
                'month': m,
                'label': date(y, m, 1).strftime('%B %Y'),
                'period_start': ps.strftime('%d %b %Y'),
                'period_end': pe.strftime('%d %b %Y'),
                'active': (y == year and m == month),
            })
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        # Departments for filter
        departments = request.env['hr.department'].sudo().search([], order='name')

        return request.render('employee_portal_suite.instant_payroll_report_page', {
            'page_name': 'instant_payroll',
            'year': year,
            'month': month,
            'period_start': period_start.strftime('%d %b %Y'),
            'period_end': period_end.strftime('%d %b %Y'),
            'periods': periods,
            'departments': departments,
            'current_month_name': date(year, month, 1).strftime('%B %Y'),
        })

    # ------------------------------------------------------------------
    # JSON API: compute report data
    # ------------------------------------------------------------------
    @http.route('/odoo/instant-payroll/data', type='json', auth='user', methods=['POST'])
    def get_report_data(self, year, month, department_id=None, employee_ids=None, **kw):
        self._require_hr_manager()

        year = int(year)
        month = int(month)
        period_start, period_end = _period_bounds(year, month)

        # ── Fetch employees ──────────────────────────────────────────
        emp_domain = [('active', '=', True)]
        if department_id:
            emp_domain.append(('department_id', '=', int(department_id)))
        if employee_ids:
            emp_domain.append(('id', 'in', employee_ids))

        employees = request.env['hr.employee'].sudo().search(emp_domain, order='name')

        # ── Public holidays in period ─────────────────────────────────
        # Odoo stores public holidays in hr.leave.public.holiday.line (if installed)
        holiday_dates = []
        if 'hr.leave.public.holiday.line' in request.env:
            ph_lines = request.env['hr.leave.public.holiday.line'].sudo().search([
                ('date', '>=', fields.Date.to_string(period_start)),
                ('date', '<=', fields.Date.to_string(period_end)),
            ])
            holiday_dates = [fields.Date.from_string(l.date) for l in ph_lines]

        expected_working_days = _working_days_in_period(period_start, period_end, holiday_dates)

        # ── Global settings ───────────────────────────────────────────
        global_hours = float(request.env['ir.config_parameter'].sudo().get_param(
            'employee_portal_suite.instant_payroll_standard_hours',
            default=str(GLOBAL_DEFAULT_HOURS)
        ))

        rows = []
        grand = {
            'gross': 0, 'deduction': 0, 'overtime': 0,
            'other_ded': 0, 'reimb': 0, 'net': 0, 'worked_hours': 0,
        }

        for emp in employees:
            row = self._compute_employee_row(
                emp, period_start, period_end,
                expected_working_days, global_hours
            )
            for k in grand:
                grand[k] += row.get(k, 0)
            rows.append(row)

        return {
            'rows': rows,
            'grand_totals': grand,
            'period_start': period_start.strftime('%d %b %Y'),
            'period_end': period_end.strftime('%d %b %Y'),
            'expected_working_days': expected_working_days,
            'global_standard_hours': global_hours,
        }

    # ------------------------------------------------------------------
    # JSON API: save a manual adjustment
    # ------------------------------------------------------------------
    @http.route('/odoo/instant-payroll/save-adjustment', type='json', auth='user', methods=['POST'])
    def save_adjustment(self, employee_id, year, month, other_deductions=0,
                        reimbursements=0, absent_days_adjustment=0, notes='', **kw):
        self._require_hr_manager()

        year, month = int(year), int(month)
        employee_id = int(employee_id)
        period_start, period_end = _period_bounds(year, month)

        Adj = request.env['hr.payroll.instant.adjustment'].sudo()
        existing = Adj.search([
            ('employee_id', '=', employee_id),
            ('period_start', '=', fields.Date.to_string(period_start)),
            ('period_end', '=', fields.Date.to_string(period_end)),
        ], limit=1)

        vals = {
            'other_deductions': float(other_deductions),
            'reimbursements': float(reimbursements),
            'absent_days_adjustment': float(absent_days_adjustment),
            'notes': notes or '',
        }

        if existing:
            existing.write(vals)
        else:
            vals.update({
                'employee_id': employee_id,
                'period_start': fields.Date.to_string(period_start),
                'period_end': fields.Date.to_string(period_end),
            })
            Adj.create(vals)

        return {'status': 'ok'}

    # ------------------------------------------------------------------
    # JSON API: push selected employees to a payroll batch
    # ------------------------------------------------------------------
    @http.route('/odoo/instant-payroll/create-payroll-batch', type='json', auth='user', methods=['POST'])
    def create_payroll_batch(self, year, month, employee_ids, **kw):
        """
        Create an hr.payroll.run (payroll batch) for the selected employees
        covering this period, then return its id and the backend URL to open it.

        Requires the hr_payroll module to be installed.
        """
        self._require_hr_manager()

        if 'hr.payroll.run' not in request.env:
            return {
                'status': 'error',
                'message': 'The Payroll module (hr_payroll) is not installed. '
                           'Please install it first to use this feature.'
            }

        year, month = int(year), int(month)
        period_start, period_end = _period_bounds(year, month)

        batch_name = f"Instant Report — {date(year, month, 1).strftime('%B %Y')}"

        try:
            batch = request.env['hr.payroll.run'].sudo().create({
                'name': batch_name,
                'date_start': fields.Date.to_string(period_start),
                'date_end': fields.Date.to_string(period_end),
            })

            # Create payslips for selected employees
            slips_created = 0
            for emp_id in employee_ids:
                emp = request.env['hr.employee'].sudo().browse(int(emp_id))
                contract = request.env['hr.contract'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'open'),
                ], limit=1)
                if not contract:
                    _logger.warning(
                        'Instant Payroll → no open contract for %s (id=%d); skipping.',
                        emp.name, emp.id
                    )
                    continue

                request.env['hr.payslip'].sudo().create({
                    'name': f"Salary Slip — {emp.name} — {date(year, month, 1).strftime('%B %Y')}",
                    'employee_id': emp.id,
                    'contract_id': contract.id,
                    'payslip_run_id': batch.id,
                    'date_from': fields.Date.to_string(period_start),
                    'date_to': fields.Date.to_string(period_end),
                })
                slips_created += 1

            return {
                'status': 'ok',
                'batch_id': batch.id,
                'slips_created': slips_created,
                'batch_url': f'/web#id={batch.id}&model=hr.payroll.run&view_type=form',
            }

        except Exception as e:
            _logger.exception('Failed to create payroll batch')
            return {'status': 'error', 'message': str(e)}

    # ------------------------------------------------------------------
    # INTERNAL: compute a single employee's payroll row
    # ------------------------------------------------------------------
    def _compute_employee_row(self, emp, period_start, period_end,
                              expected_working_days, global_hours):
        """
        Replicates the AdminReports.tsx payroll engine for one employee.
        Returns a dict ready for JSON serialisation.
        """
        # ── Salary ────────────────────────────────────────────────────
        gross_salary = emp._get_effective_gross_salary()
        basic_salary = emp.instant_basic_salary or (gross_salary / 1.35)
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

        # ── Attendance (worked hours) ─────────────────────────────────
        Attendance = request.env['hr.attendance'].sudo()
        attendances = Attendance.search([
            ('employee_id', '=', emp.id),
            ('check_in', '>=', fields.Datetime.to_string(
                datetime.combine(period_start, datetime.min.time()))),
            ('check_in', '<=', fields.Datetime.to_string(
                datetime.combine(period_end, datetime.max.time()))),
        ])

        worked_hours = sum(a.worked_hours or 0.0 for a in attendances)
        shift_count = len(attendances)

        # Days worked = distinct calendar dates with at least one check-in
        days_worked_set = set()
        for att in attendances:
            if att.check_in:
                # Convert UTC → employee tz to get the local date
                tz_name = emp.tz or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except Exception:
                    tz = pytz.utc
                local_dt = pytz.utc.localize(att.check_in).astimezone(tz)
                days_worked_set.add(local_dt.date())
        days_worked = len(days_worked_set)

        # ── Approved absences from hr.leave ───────────────────────────
        Leave = request.env['hr.leave'].sudo()
        approved_leaves = Leave.search([
            ('employee_id', '=', emp.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Date.to_string(period_end)),
            ('date_to', '>=', fields.Date.to_string(period_start)),
        ])

        # Sum the number of days within our period window
        absent_days_from_leave = 0.0
        for leave in approved_leaves:
            leave_start = max(fields.Date.from_string(leave.date_from), period_start)
            leave_end = min(fields.Date.from_string(leave.date_to), period_end)
            if leave_start <= leave_end:
                # number_of_days_display already excludes weekends/holidays in Odoo
                # but we recompute for our window to be safe
                d = leave_start
                while d <= leave_end:
                    if d.weekday() not in (4, 5):  # exclude Fri+Sat
                        absent_days_from_leave += 1
                    d += timedelta(days=1)

        # ── Manual adjustment ─────────────────────────────────────────
        Adj = request.env['hr.payroll.instant.adjustment'].sudo()
        adj_rec = Adj.search([
            ('employee_id', '=', emp.id),
            ('period_start', '=', fields.Date.to_string(period_start)),
            ('period_end', '=', fields.Date.to_string(period_end)),
        ], limit=1)

        adj_other_ded = adj_rec.other_deductions if adj_rec else 0.0
        adj_reimbursements = adj_rec.reimbursements if adj_rec else 0.0
        adj_absent_days = adj_rec.absent_days_adjustment if adj_rec else 0.0

        total_absent_days = absent_days_from_leave + adj_absent_days

        # ── Hourly deduction (identical to Attendance Pro refactored logic) ──
        # Shortfall is computed only on days actually worked, not absent days.
        days_for_calc = expected_working_days if expected_working_days > 0 else GLOBAL_DEFAULT_WORKING_DAYS
        theoretical_hours_per_day = target_hours / days_for_calc
        expected_hours_for_days_worked = days_worked * theoretical_hours_per_day
        hourly_shortfall = max(0.0, expected_hours_for_days_worked - worked_hours)

        hourly_deduction = (hourly_shortfall * gross_hourly_rate) if (hourly_shortfall > 0.01 and ded_enabled) else 0.0
        absent_deduction = (total_absent_days * daily_rate) if ded_enabled else 0.0
        total_deduction = hourly_deduction + absent_deduction

        # ── Overtime ─────────────────────────────────────────────────
        diff = worked_hours - target_hours
        overtime_pay = (diff * overtime_hourly_rate) if (diff > 0.01 and ot_enabled) else 0.0

        # ── Net salary ────────────────────────────────────────────────
        other_ded_total = adj_other_ded + fixed_deductions
        net_salary = gross_salary - total_deduction + overtime_pay - other_ded_total + adj_reimbursements

        # ── Annual leave balance ──────────────────────────────────────
        leave_balance = 0.0
        leave_taken_ytd = 0.0
        leave_allocation_total = 0.0
        if 'hr.leave.allocation' in request.env:
            today = date.today()
            allocations = request.env['hr.leave.allocation'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'validate'),
                ('holiday_status_id.active', '=', True),
            ])
            # Sum allocations for annual leave types only
            for alloc in allocations:
                if alloc.holiday_status_id.leave_validation_type in ('both', 'manager'):
                    leave_allocation_total += alloc.number_of_days

            # Taken days (validated) current year
            taken_leaves = request.env['hr.leave'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'validate'),
                ('date_from', '>=', f'{today.year}-01-01'),
                ('date_to', '<=', f'{today.year}-12-31'),
            ])
            leave_taken_ytd = sum(
                l.number_of_days for l in taken_leaves
                if l.holiday_status_id.leave_validation_type in ('both', 'manager')
            )
            leave_balance = leave_allocation_total - leave_taken_ytd

        # ── Time-off status this period ───────────────────────────────
        is_on_leave_now = any(
            fields.Date.from_string(l.date_from) <= date.today() <= fields.Date.from_string(l.date_to)
            for l in approved_leaves
        ) if approved_leaves else False

        return {
            'id': emp.id,
            'name': emp.name,
            'department': emp.department_id.name or '',
            'job': emp.job_id.name or '',
            'is_on_leave_now': is_on_leave_now,

            # Attendance stats
            'worked_hours': round(worked_hours, 2),
            'shift_count': shift_count,
            'days_worked': days_worked,
            'expected_working_days': expected_working_days,
            'diff': round(diff, 2),
            'target_hours': round(target_hours, 2),

            # Absence
            'absent_days_from_leave': round(absent_days_from_leave, 2),
            'adj_absent_days': round(adj_absent_days, 2),
            'total_absent_days': round(total_absent_days, 2),

            # Salary components
            'gross': round(gross_salary, 2),
            'basic_salary': round(basic_salary, 2),
            'housing_allowance': round(housing_allowance, 2),
            'other_allowances': round(other_allowances, 2),
            'fixed_deductions': round(fixed_deductions, 2),

            # Deductions
            'absent_deduction': round(absent_deduction, 2),
            'hourly_deduction': round(hourly_deduction, 2),
            'hourly_shortfall': round(hourly_shortfall, 2),
            'deduction': round(total_deduction, 2),
            'other_ded': round(other_ded_total, 2),
            'adj_other_ded': round(adj_other_ded, 2),

            # OT & reimbursements
            'overtime': round(overtime_pay, 2),
            'overtime_hours': round(max(0.0, diff), 2),
            'reimb': round(adj_reimbursements, 2),

            # Net
            'net': round(net_salary, 2),

            # Leave balance (annual)
            'leave_allocation_total': round(leave_allocation_total, 2),
            'leave_taken_ytd': round(leave_taken_ytd, 2),
            'leave_balance': round(leave_balance, 2),

            # WPS
            'iqama_number': emp.iqama_number or '',
            'bank_code': emp.bank_code or '',
            'iban_number': emp.iban_number or '',

            # Flags
            'ot_enabled': ot_enabled,
            'ded_enabled': ded_enabled,
        }
