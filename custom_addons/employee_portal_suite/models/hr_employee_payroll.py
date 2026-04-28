# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Do not duplicate Saudi localization fields already present on employee/contract:
    # - Iqama/National ID: l10n_sa_employee_code on hr.employee
    # - IBAN/bank account: bank_account_id on hr.employee
    # - Salary/allowances: wage, l10n_sa_housing_allowance,
    #   l10n_sa_transportation_allowance, l10n_sa_other_allowances on hr.contract
    # Only keep fields that are not standard/localization fields.
    eps_bank_code = fields.Char(
        string='Mudad Bank Code',
        size=4,
        help='Four-character Mudad/WPS bank code, for example RJHI. If empty, the export tries to use the bank BIC/code from the employee bank account.',
    )
    eps_disable_overtime = fields.Boolean(string='Disable Overtime', default=True)
    eps_disable_deductions = fields.Boolean(string='Disable Attendance Deductions')
    eps_is_on_leave = fields.Boolean(string='On Leave')
    eps_leave_start_date = fields.Date(string='Leave Start')
    eps_leave_end_date = fields.Date(string='Leave End')
