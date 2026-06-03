"""
Instant Payroll Report Controller — Odoo 19
============================================
Replicates the Attendance Pro "Instance Report" live 26th→25th payroll
computation using data already in Odoo:

  hr.attendance               → worked hours, check-in/out records
  hr.leave                    → approved absences (absence days)
  hr.leave.allocation         → annual leave balance
  hr.employee                 → salary & WPS fields (custom tab)
  hr.contract                 → wage fallback
  hr.payroll.instant.adjustment → manual adjustments per employee/period

Salary maths are identical to Attendance Pro AdminReports.tsx:
  grossHourlyRate      = gross / 240
  basicHourlyRate      = (gross / 1.35) / 240
  overtimeHourlyRate   = grossHourlyRate + 0.5 * basicHourlyRate
  dailyRate            = gross / 30
  hourlyShortfall      = max(0, expectedHoursForDaysWorked − workedHours)
  hourlyDeduction      = hourlyShortfall * grossHourlyRate  (if deductions enabled)
  absentDeduction      = absentDays * dailyRate             (if deductions enabled)
  overtimePay          = overtimeHours * overtimeHourlyRate (if OT enabled)
  net                  = gross − totalDeduction + OT − otherDed + reimbursements
"""

import json
import logging
from datetime import date, datetime, timedelta

import pytz

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

GLOBAL_DEFAULT_HOURS = 240.0
GLOBAL_DEFAULT_WORKING_DAYS = 26


# ── Period helpers ────────────────────────────────────────────────────────────

def _period_bounds(year: int, month: int):
    """
    26th of previous month → 25th of given month.
    e.g. month=6 → (May 26, June 25)
    """
    end = date(year, month, 25)
    if month == 1:
        start = date(year - 1, 12, 26)
    else:
        start = date(year, month - 1, 26)
    return start, end


def _working_days_in_period(start: date, end: date, holiday_dates=None):
    """
    Count working days (Sun–Thu for Saudi Arabia, i.e. skip Fri=4 and Sat=5).
    Subtracts any public holidays that fall on a working day.
    """
    holiday_dates = set(holiday_dates or [])
    count = 0
    current = start
    while current <= end:
        if current.weekday() not in (4, 5) and current not in holiday_dates:
            count += 1
        current += timedelta(days=1)
    return count


# ── Controller ────────────────────────────────────────────────────────────────

class InstantPayrollController(http.Controller):

    # ── Access guard ──────────────────────────────────────────────────
    def _require_payroll_access(self):
        user = request.env.user
        allowed = (
            user.has_group('hr.group_hr_manager') or
            user.has_group('base.group_system') or
            user.has_group('employee_portal_suite.group_employee_portal_hr') or
            user.has_group('employee_portal_suite.group_employee_portal_admin')
        )
        if not allowed:
            raise request.not_found()

    # ── Main page ─────────────────────────────────────────────────────
    @http.route('/my/instant-payroll', type='http', auth='user', website=True)
    def instant_payroll_page(self, year=None, month=None, **kw):
        self._require_payroll_access()

        today = date.today()
        try:
            year  = int(year)  if year  else today.year
            month = int(month) if month else today.month
        except (TypeError, ValueError):
            year, month = today.year, today.month

        period_start, period_end = _period_bounds(year, month)

        # Last 13 months for navigation
        periods = []
        y, m = today.year, today.month
        for _ in range(13):
            ps, pe = _period_bounds(y, m)
            periods.append({
                'year':         y,
                'month':        m,
                'label':        date(y, m, 1).strftime('%B %Y'),
                'period_start': ps.strftime('%d %b %Y'),
                'period_end':   pe.strftime('%d %b %Y'),
                'active':       (y == year and m == month),
            })
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        departments = request.env['hr.department'].sudo().search([], order='name')

        return request.render('employee_portal_suite.instant_payroll_report_page', {
            'page_name':          'instant_payroll',
            'year':               year,
            'month':              month,
            'period_start':       period_start.strftime('%d %b %Y'),
            'period_end':         period_end.strftime('%d %b %Y'),
            'periods':            periods,
            'departments':        departments,
            'current_month_name': date(year, month, 1).strftime('%B %Y'),
        })

    # ── JSON API: compute report ──────────────────────────────────────
    @http.route('/my/instant-payroll/data', type='http', auth='user',
                methods=['POST'], csrf=True)
    def get_report_data(self, **post):
        self._require_payroll_access()

        year          = int(post.get('year',          date.today().year))
        month         = int(post.get('month',         date.today().month))
        department_id = post.get('department_id') or None
        period_start, period_end = _period_bounds(year, month)

        # Employees
        domain = [('active', '=', True)]
        if department_id:
            domain.append(('department_id', '=', int(department_id)))
        employees = request.env['hr.employee'].sudo().search(domain, order='name')

        # Public holidays
        holiday_dates = []
        if 'hr.leave.public.holiday.line' in request.env:
            ph = request.env['hr.leave.public.holiday.line'].sudo().search([
                ('date', '>=', fields.Date.to_string(period_start)),
                ('date', '<=', fields.Date.to_string(period_end)),
            ])
            holiday_dates = [fields.Date.from_string(l.date) for l in ph]

        expected_days = _working_days_in_period(period_start, period_end, holiday_dates)

        global_hours = float(
            request.env['ir.config_parameter'].sudo().get_param(
                'employee_portal_suite.instant_payroll_standard_hours',
                default=str(GLOBAL_DEFAULT_HOURS)
            )
        )

        rows = []
        grand = dict(gross=0, deduction=0, overtime=0,
                     other_ded=0, reimb=0, net=0, worked_hours=0)

        for emp in employees:
            row = self._compute_row(emp, period_start, period_end,
                                    expected_days, global_hours)
            for k in grand:
                grand[k] += row.get(k, 0)
            rows.append(row)

        payload = json.dumps({
            'rows':                   rows,
            'grand_totals':           grand,
            'period_start':           period_start.strftime('%d %b %Y'),
            'period_end':             period_end.strftime('%d %b %Y'),
            'expected_working_days':  expected_days,
            'global_standard_hours':  global_hours,
        })
        return request.make_response(payload,
                                     headers=[('Content-Type', 'application/json')])

    # ── JSON API: save adjustment ─────────────────────────────────────
    @http.route('/my/instant-payroll/save-adjustment', type='http',
                auth='user', methods=['POST'], csrf=True)
    def save_adjustment(self, **post):
        self._require_payroll_access()

        employee_id   = int(post.get('employee_id', 0))
        year          = int(post.get('year',  date.today().year))
        month         = int(post.get('month', date.today().month))
        other_ded     = float(post.get('other_deductions',      0) or 0)
        reimb         = float(post.get('reimbursements',        0) or 0)
        absent_adj    = float(post.get('absent_days_adjustment', 0) or 0)
        notes         = post.get('notes', '')

        period_start, period_end = _period_bounds(year, month)
        Adj = request.env['hr.payroll.instant.adjustment'].sudo()

        existing = Adj.search([
            ('employee_id', '=', employee_id),
            ('period_start', '=', fields.Date.to_string(period_start)),
            ('period_end',   '=', fields.Date.to_string(period_end)),
        ], limit=1)

        vals = {
            'other_deductions':      other_ded,
            'reimbursements':        reimb,
            'absent_days_adjustment': absent_adj,
            'notes':                 notes,
        }
        if existing:
            existing.write(vals)
        else:
            vals.update({
                'employee_id': employee_id,
                'period_start': fields.Date.to_string(period_start),
                'period_end':   fields.Date.to_string(period_end),
            })
            Adj.create(vals)

        return request.make_response(
            json.dumps({'status': 'ok'}),
            headers=[('Content-Type', 'application/json')]
        )

    # ── JSON API: create payroll batch ────────────────────────────────
    @http.route('/my/instant-payroll/create-batch', type='http',
                auth='user', methods=['POST'], csrf=True)
    def create_payroll_batch(self, **post):
        self._require_payroll_access()

        if 'hr.payroll.run' not in request.env:
            return request.make_response(
                json.dumps({'status': 'error',
                            'message': 'The Payroll module (hr_payroll) is not installed.'}),
                headers=[('Content-Type', 'application/json')]
            )

        year         = int(post.get('year',  date.today().year))
        month        = int(post.get('month', date.today().month))
        employee_ids = json.loads(post.get('employee_ids', '[]'))

        period_start, period_end = _period_bounds(year, month)
        batch_name = f"Instant Report — {date(year, month, 1).strftime('%B %Y')}"

        try:
            batch = request.env['hr.payroll.run'].sudo().create({
                'name':       batch_name,
                'date_start': fields.Date.to_string(period_start),
                'date_end':   fields.Date.to_string(period_end),
            })
            slips = 0
            for eid in employee_ids:
                emp = request.env['hr.employee'].sudo().browse(int(eid))
                contract = request.env['hr.contract'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'open'),
                ], limit=1)
                if not contract:
                    _logger.warning('Instant Payroll batch: no open contract for %s', emp.name)
                    continue
                request.env['hr.payslip'].sudo().create({
                    'name':            f"Salary — {emp.name} — {date(year, month, 1).strftime('%B %Y')}",
                    'employee_id':     emp.id,
                    'contract_id':     contract.id,
                    'payslip_run_id':  batch.id,
                    'date_from':       fields.Date.to_string(period_start),
                    'date_to':         fields.Date.to_string(period_end),
                })
                slips += 1

            return request.make_response(
                json.dumps({
                    'status':        'ok',
                    'batch_id':      batch.id,
                    'slips_created': slips,
                    'batch_url':     f'/odoo/payroll/{batch.id}',
                }),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            _logger.exception('Failed to create payroll batch')
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )

    # ── Core payroll engine ───────────────────────────────────────────
    def _compute_row(self, emp, period_start, period_end, expected_days, global_hours):
        """
        Compute one employee's payroll row.
        Replicates AdminReports.tsx logic exactly.
        """
        # ── Salary ────────────────────────────────────────────────────
        gross         = emp._get_effective_gross_salary()
        basic         = emp.instant_basic_salary or (gross / 1.35 if gross else 0.0)
        housing       = emp.instant_housing_allowance   or 0.0
        other_allow   = emp.instant_other_allowances    or 0.0
        fixed_ded     = emp.instant_fixed_deductions    or 0.0
        target_hours  = emp.instant_standard_hours      or global_hours
        ot_enabled    = not emp.instant_disable_overtime
        ded_enabled   = not emp.instant_disable_deductions

        daily_rate         = gross / 30.0          if gross else 0.0
        gross_hourly       = gross / 240.0         if gross else 0.0
        basic_hourly       = basic / 240.0         if basic else 0.0
        overtime_rate      = gross_hourly + 0.5 * basic_hourly

        # ── Attendance ────────────────────────────────────────────────
        dt_start = fields.Datetime.to_string(
            datetime.combine(period_start, datetime.min.time()))
        dt_end   = fields.Datetime.to_string(
            datetime.combine(period_end,   datetime.max.time()))

        attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', emp.id),
            ('check_in',    '>=', dt_start),
            ('check_in',    '<=', dt_end),
        ])

        worked_hours = sum(a.worked_hours or 0.0 for a in attendances)
        shift_count  = len(attendances)

        # Days worked = unique local-date check-ins
        tz_name = emp.tz or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.utc

        days_worked_set = set()
        for att in attendances:
            if att.check_in:
                local_dt = pytz.utc.localize(att.check_in).astimezone(tz)
                days_worked_set.add(local_dt.date())
        days_worked = len(days_worked_set)

        # ── Approved absences ─────────────────────────────────────────
        approved_leaves = request.env['hr.leave'].sudo().search([
            ('employee_id', '=', emp.id),
            ('state',       '=', 'validate'),
            ('date_from',   '<=', fields.Date.to_string(period_end)),
            ('date_to',     '>=', fields.Date.to_string(period_start)),
        ])

        absent_from_leave = 0.0
        for leave in approved_leaves:
            ls = max(fields.Date.from_string(str(leave.date_from)[:10]), period_start)
            le = min(fields.Date.from_string(str(leave.date_to)[:10]),   period_end)
            d = ls
            while d <= le:
                if d.weekday() not in (4, 5):
                    absent_from_leave += 1
                d += timedelta(days=1)

        is_on_leave_now = any(
            fields.Date.from_string(str(l.date_from)[:10]) <= date.today()
            <= fields.Date.from_string(str(l.date_to)[:10])
            for l in approved_leaves
        ) if approved_leaves else False

        # ── Manual adjustment ─────────────────────────────────────────
        adj = request.env['hr.payroll.instant.adjustment'].sudo().search([
            ('employee_id', '=', emp.id),
            ('period_start', '=', fields.Date.to_string(period_start)),
            ('period_end',   '=', fields.Date.to_string(period_end)),
        ], limit=1)

        adj_other_ded  = adj.other_deductions      if adj else 0.0
        adj_reimb      = adj.reimbursements         if adj else 0.0
        adj_absent     = adj.absent_days_adjustment if adj else 0.0

        total_absent   = absent_from_leave + adj_absent

        # ── Hourly shortfall (only on days actually worked) ───────────
        days_for_calc   = expected_days if expected_days > 0 else GLOBAL_DEFAULT_WORKING_DAYS
        hours_per_day   = target_hours / days_for_calc
        expected_worked = days_worked * hours_per_day
        shortfall       = max(0.0, expected_worked - worked_hours)

        hourly_ded = (shortfall * gross_hourly) if (shortfall > 0.01 and ded_enabled) else 0.0
        absent_ded = (total_absent * daily_rate) if ded_enabled                        else 0.0
        total_ded  = hourly_ded + absent_ded

        # ── Overtime ──────────────────────────────────────────────────
        diff       = worked_hours - target_hours
        ot_pay     = (diff * overtime_rate) if (diff > 0.01 and ot_enabled) else 0.0

        # ── Net ───────────────────────────────────────────────────────
        other_ded_total = adj_other_ded + fixed_ded
        net = gross - total_ded + ot_pay - other_ded_total + adj_reimb

        # ── Annual leave balance ──────────────────────────────────────
        leave_alloc_total = 0.0
        leave_taken_ytd   = 0.0
        if 'hr.leave.allocation' in request.env:
            today = date.today()
            allocs = request.env['hr.leave.allocation'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state',       '=', 'validate'),
            ])
            for a in allocs:
                if hasattr(a.holiday_status_id, 'leave_validation_type') and \
                   a.holiday_status_id.leave_validation_type in ('both', 'manager'):
                    leave_alloc_total += a.number_of_days

            taken = request.env['hr.leave'].sudo().search([
                ('employee_id', '=', emp.id),
                ('state',       '=', 'validate'),
                ('date_from',   '>=', f'{today.year}-01-01'),
                ('date_to',     '<=', f'{today.year}-12-31'),
            ])
            for l in taken:
                if hasattr(l.holiday_status_id, 'leave_validation_type') and \
                   l.holiday_status_id.leave_validation_type in ('both', 'manager'):
                    leave_taken_ytd += l.number_of_days

        leave_balance = leave_alloc_total - leave_taken_ytd

        return {
            'id':         emp.id,
            'name':       emp.name,
            'department': emp.department_id.name if emp.department_id else '',
            'job':        emp.job_id.name        if emp.job_id        else '',
            'is_on_leave_now': is_on_leave_now,

            # Attendance
            'worked_hours':        round(worked_hours, 2),
            'shift_count':         shift_count,
            'days_worked':         days_worked,
            'expected_days':       expected_days,
            'target_hours':        round(target_hours, 2),
            'diff':                round(diff, 2),

            # Absences
            'absent_from_leave':   round(absent_from_leave, 2),
            'adj_absent':          round(adj_absent, 2),
            'total_absent':        round(total_absent, 2),

            # Salary
            'gross':               round(gross, 2),
            'basic':               round(basic, 2),
            'housing':             round(housing, 2),
            'other_allowances':    round(other_allow, 2),
            'fixed_ded':           round(fixed_ded, 2),

            # Deductions
            'absent_ded':          round(absent_ded, 2),
            'hourly_ded':          round(hourly_ded, 2),
            'shortfall_hours':     round(shortfall, 2),
            'deduction':           round(total_ded, 2),
            'other_ded':           round(other_ded_total, 2),
            'adj_other_ded':       round(adj_other_ded, 2),

            # OT & reimb
            'overtime':            round(ot_pay, 2),
            'overtime_hours':      round(max(0.0, diff), 2),
            'reimb':               round(adj_reimb, 2),

            # Net
            'net':                 round(net, 2),

            # Leave balance
            'leave_alloc_total':   round(leave_alloc_total, 2),
            'leave_taken_ytd':     round(leave_taken_ytd, 2),
            'leave_balance':       round(leave_balance, 2),

            # WPS
            'iqama_number': emp.iqama_number  or '',
            'bank_code':    emp.bank_code     or '',
            'iban_number':  emp.iban_number   or '',

            # Flags
            'ot_enabled':  ot_enabled,
            'ded_enabled': ded_enabled,
        }
