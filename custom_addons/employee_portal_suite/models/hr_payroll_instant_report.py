from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HrPayrollInstantAdjustment(models.Model):
    """
    Stores manual payroll adjustments per employee per payroll period.
    Period runs from the 26th of the previous month to the 25th of
    the current month — identical to the Attendance Pro instance report cycle.
    """
    _name = 'hr.payroll.instant.adjustment'
    _description = 'Instant Payroll Report Adjustment'
    _rec_name = 'employee_id'
    _order = 'period_start desc, employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, ondelete='cascade', index=True
    )
    period_start = fields.Date(string='Period Start (26th)', required=True)
    period_end   = fields.Date(string='Period End (25th)',   required=True)

    other_deductions = fields.Float(
        string='Other Deductions (SAR)', default=0.0,
        help='Extra deductions for this period (advances, penalties, etc.)'
    )
    reimbursements = fields.Float(
        string='Reimbursements (SAR)', default=0.0,
        help='Extra additions for this period (expense claims, etc.)'
    )
    absent_days_adjustment = fields.Float(
        string='Absent Days Adjustment', default=0.0,
        help='Additional absent days on top of the leave-computed count.'
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_employee_period',
         'UNIQUE(employee_id, period_start, period_end)',
         'An adjustment record already exists for this employee and period.'),
    ]


class HrEmployee(models.Model):
    """
    Extend hr.employee with instant payroll salary fields and WPS data.
    Mirrors the User type in Attendance Pro (grossSalary, standardHours, etc.)
    """
    _inherit = 'hr.employee'

    # ── Salary fields ───────────────────────────────────────────────────
    instant_gross_salary = fields.Float(
        string='Gross Salary (SAR)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
        help='Total gross monthly salary used by the Instant Payroll Report. '
             'Leave 0 to fall back to the active hr.contract wage.'
    )
    instant_basic_salary = fields.Float(
        string='Basic Salary Component (SAR)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
        help='WPS export field. If 0, computed automatically as Gross / 1.35.'
    )
    instant_housing_allowance = fields.Float(
        string='Housing Allowance (SAR)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )
    instant_other_allowances = fields.Float(
        string='Other Allowances (SAR)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )
    instant_fixed_deductions = fields.Float(
        string='Fixed Monthly Deductions (SAR)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
        help='Fixed deductions applied every month (e.g. GOSI employee share).'
    )
    instant_standard_hours = fields.Float(
        string='Standard Monthly Hours',
        default=0.0,
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
        help='Target hours per payroll period. Leave 0 to use the global default (240 h).'
    )
    instant_disable_overtime = fields.Boolean(
        string='Disable Overtime Pay',
        default=False,
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )
    instant_disable_deductions = fields.Boolean(
        string='Disable Hour/Day Deductions',
        default=False,
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )

    # ── WPS / Mudad fields ──────────────────────────────────────────────
    iqama_number = fields.Char(
        string='Iqama / National ID (10 digits)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )
    bank_code = fields.Char(
        string='Bank Code (4 chars, e.g. RJHI)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )
    iban_number = fields.Char(
        string='IBAN (SA… 24 chars)',
        groups='hr.group_hr_manager,employee_portal_suite.group_employee_portal_hr',
    )

    def _get_effective_gross_salary(self):
        """
        Return the gross salary for instant report calculations.
        Priority:
          1. instant_gross_salary (manually set on employee tab)
          2. Active hr.contract wage (if hr_payroll is installed)
          3. 0
        """
        self.ensure_one()
        if self.instant_gross_salary:
            return self.instant_gross_salary
        if 'hr.contract' in self.env:
            contract = self.env['hr.contract'].sudo().search([
                ('employee_id', '=', self.id),
                ('state', '=', 'open'),
            ], limit=1)
            if contract and contract.wage:
                return float(contract.wage)
        return 0.0
