from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HrPayrollInstantAdjustment(models.Model):
    """
    Stores manual payroll adjustments per employee per period —
    mirrors the 'payroll_adjustments' Firestore collection used in
    Attendance Pro's instance report.

    One record = one employee × one payroll period (26th → 25th).
    """
    _name = 'hr.payroll.instant.adjustment'
    _description = 'Instant Payroll Report Adjustment'
    _rec_name = 'employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        required=True, ondelete='cascade', index=True
    )
    period_start = fields.Date(string='Period Start (26th)', required=True)
    period_end = fields.Date(string='Period End (25th)', required=True)

    other_deductions = fields.Float(
        string='Other Deductions (SAR)', default=0.0,
        help='Manual additional deductions for this period (e.g. advances, penalties).'
    )
    reimbursements = fields.Float(
        string='Reimbursements (SAR)', default=0.0,
        help='Manual additions for this period (e.g. expense reimbursements).'
    )
    absent_days_adjustment = fields.Float(
        string='Absent Days Adjustment', default=0.0,
        help='Additional absent days to add on top of the computed count.'
    )
    notes = fields.Text(string='Notes')

    _sql_constraints = [
        ('unique_employee_period',
         'UNIQUE(employee_id, period_start, period_end)',
         'An adjustment record already exists for this employee and period.')
    ]


class HrEmployee(models.Model):
    """Extend hr.employee with payroll fields that match Attendance Pro's User type."""
    _inherit = 'hr.employee'

    # ── Salary override fields (if not using hr_payroll wage) ──────────
    instant_gross_salary = fields.Float(
        string='Gross Salary (SAR)',
        help='Total gross monthly salary used by the Instant Payroll Report. '
             'Leave 0 to pull from the active payroll contract wage.'
    )
    instant_basic_salary = fields.Float(
        string='Basic Salary Component (SAR)',
        help='Used for WPS export. If 0, computed as Gross / 1.35.'
    )
    instant_housing_allowance = fields.Float(
        string='Housing Allowance (SAR)',
        help='Used for WPS export.'
    )
    instant_other_allowances = fields.Float(
        string='Other Allowances (SAR)',
        help='Used for WPS export.'
    )
    instant_fixed_deductions = fields.Float(
        string='Fixed Monthly Deductions (SAR)',
        help='Fixed deductions applied every month (e.g. GOSI employee share).'
    )
    instant_standard_hours = fields.Float(
        string='Standard Monthly Hours',
        default=0,
        help='Target hours per payroll period. Leave 0 to use the global default (240 h).'
    )
    instant_disable_overtime = fields.Boolean(
        string='Disable Overtime Pay', default=False
    )
    instant_disable_deductions = fields.Boolean(
        string='Disable Hour/Day Deductions', default=False
    )

    # ── WPS / Mudad fields ──────────────────────────────────────────────
    iqama_number = fields.Char(
        string='Iqama / National ID',
        help='10-digit national or iqama number, required for Mudad WPS export.'
    )
    bank_code = fields.Char(
        string='Bank Code (4 chars)',
        help='4-character bank short code, e.g. RJHI.'
    )
    iban_number = fields.Char(
        string='IBAN (SA…)',
        help='24-character Saudi IBAN starting with SA.'
    )

    def _get_effective_gross_salary(self):
        """
        Return the gross salary to use for instant report calculations.
        Priority:
          1. instant_gross_salary (manually set on employee)
          2. Active payroll contract wage (hr.payroll.contract if installed)
          3. 0
        """
        self.ensure_one()
        if self.instant_gross_salary:
            return self.instant_gross_salary
        # Try reading from a linked payroll contract if hr_payroll is installed
        if 'hr.contract' in self.env:
            contract = self.env['hr.contract'].sudo().search([
                ('employee_id', '=', self.id),
                ('state', '=', 'open'),
            ], limit=1)
            if contract:
                return contract.wage or 0.0
        return 0.0
