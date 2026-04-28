# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Optional payroll/Mudad override fields.
    # Leave these empty to use the existing Saudi/Odoo fields:
    # - Iqama/National ID: l10n_sa_employee_code on hr.employee
    # - IBAN/bank account: bank_account_id.acc_number on hr.employee
    # - Salary/allowances: wage, l10n_sa_housing_allowance,
    #   l10n_sa_transportation_allowance, l10n_sa_other_allowances on hr.contract
    eps_iqama_number = fields.Char(string='Iqama / National ID Override', size=10)
    eps_iban_number = fields.Char(string='IBAN Override', help='Leave empty to use the employee bank account IBAN.')
    eps_bank_code = fields.Char(
        string='Mudad Bank Code',
        size=4,
        help='Four-character Mudad/WPS bank code, for example RJHI. If empty, the export tries to use the bank BIC/code from the employee bank account.',
    )

    eps_gross_salary = fields.Float(string='Gross Salary Override')
    eps_basic_salary = fields.Float(string='Basic Salary Override')
    eps_housing_allowance = fields.Float(string='Housing Allowance Override')
    eps_other_allowances = fields.Float(string='Other Allowances Override')
    eps_fixed_deductions = fields.Float(string='Fixed Monthly Deductions Override')
    eps_standard_monthly_hours = fields.Float(string='Standard Monthly Hours Override')

    eps_disable_overtime = fields.Boolean(string='Disable Overtime', default=True)
    eps_disable_deductions = fields.Boolean(string='Disable Attendance Deductions')
    eps_is_on_leave = fields.Boolean(string='On Leave')
    eps_leave_start_date = fields.Date(string='Leave Start')
    eps_leave_end_date = fields.Date(string='Leave End')
