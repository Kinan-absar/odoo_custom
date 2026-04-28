# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    eps_iqama_number = fields.Char(string='Iqama / National ID', size=10)
    eps_bank_code = fields.Char(string='Mudad Bank Code', size=4, help='Four-character Mudad/WPS bank code, for example RJHI.')
    eps_iban_number = fields.Char(string='IBAN', help='Saudi IBAN, 24 characters and starts with SA.')
    eps_gross_salary = fields.Float(string='Gross Salary')
    eps_basic_salary = fields.Float(string='Basic Salary')
    eps_housing_allowance = fields.Float(string='Housing Allowance')
    eps_other_allowances = fields.Float(string='Other Allowances')
    eps_fixed_deductions = fields.Float(string='Fixed Monthly Deductions')
    eps_standard_monthly_hours = fields.Float(string='Standard Monthly Hours', default=240.0)
    eps_disable_overtime = fields.Boolean(string='Disable Overtime')
    eps_disable_deductions = fields.Boolean(string='Disable Attendance Deductions')
    eps_is_on_leave = fields.Boolean(string='On Leave')
    eps_leave_start_date = fields.Date(string='Leave Start')
    eps_leave_end_date = fields.Date(string='Leave End')
