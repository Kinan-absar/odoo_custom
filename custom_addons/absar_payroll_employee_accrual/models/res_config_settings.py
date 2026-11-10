from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    payroll_accrued_salary_account_id = fields.Many2one(
        related="company_id.payroll_accrued_salary_account_id",
        readonly=False,
        string="Accrued Salary Account",
        help=(
            "Liability account that must stay split by employee/partner inside "
            "the single batched payroll journal entry."
        ),
    )
