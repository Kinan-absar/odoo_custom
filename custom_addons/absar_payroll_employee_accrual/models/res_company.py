from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    payroll_accrued_salary_account_id = fields.Many2one(
        "account.account",
        string="Payroll Accrued Salary Account",
        domain="[('deprecated', '=', False)]",
        check_company=True,
        help=(
            "Liability account that must stay split by employee/partner inside "
            "the single batched payroll journal entry. Example: 203003 Accrued - Salaries."
        ),
    )
