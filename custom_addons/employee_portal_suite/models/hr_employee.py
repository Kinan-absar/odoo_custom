# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Payroll/attendance report controls used by the instant salary report views.
    # Defaults keep the previous behavior: attendance is required, deductions and overtime are enabled.
    eps_attendance_not_required = fields.Boolean(
        string='Attendance Not Applicable',
        help='If enabled, the instant salary report uses fixed/standard hours instead of attendance worked hours.'
    )
    eps_fixed_worked_hours = fields.Float(
        string='Fixed Worked Hours',
        help='Fixed hours to use in the instant salary report when attendance is not applicable. If empty, target hours are used.'
    )
    eps_overtime_enabled = fields.Boolean(
        string='Overtime Enabled',
        default=True,
        help='Allow overtime calculation in the instant salary report.'
    )
    eps_deduction_enabled = fields.Boolean(
        string='Attendance Deduction Enabled',
        default=True,
        help='Allow attendance shortage/absence deduction in the instant salary report.'
    )

    eps_target_hours = fields.Float(
        string='Target Hours',
        help='Monthly target hours used by the instant salary report. If empty, the report uses the working schedule or default period target.'
    )
    eps_housing_allowance = fields.Monetary(
        string='Housing Allowance',
        currency_field='currency_id',
        help='Housing allowance amount used to split gross salary into basic salary for overtime premium calculation.'
    )
    eps_transport_allowance = fields.Monetary(
        string='Transport Allowance',
        currency_field='currency_id',
        help='Transport allowance amount used to split gross salary into basic salary for overtime premium calculation.'
    )
    eps_other_allowance = fields.Monetary(
        string='Other Allowance',
        currency_field='currency_id',
        help='Other allowance amount used to split gross salary into basic salary for overtime premium calculation.'
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
        string='Currency'
    )
