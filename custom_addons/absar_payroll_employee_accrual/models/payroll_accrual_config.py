from odoo import api, fields, models


class AbsarPayrollAccrualConfig(models.TransientModel):
    _name = "absar.payroll.accrual.config"
    _description = "Employee Accrued Salary Configuration"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    accrued_salary_account_id = fields.Many2one(
        "account.account",
        string="Accrued Salary Account",
        required=True,
        domain="[('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        check_company=True,
        help=(
            "Liability account that must stay split by employee/partner inside "
            "the single batched payroll journal entry."
        ),
    )

    @api.onchange("company_id")
    def _onchange_company_id(self):
        for wizard in self:
            wizard.accrued_salary_account_id = wizard.company_id.payroll_accrued_salary_account_id

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        if "company_id" in fields_list:
            values["company_id"] = company.id
        if "accrued_salary_account_id" in fields_list:
            values["accrued_salary_account_id"] = company.payroll_accrued_salary_account_id.id
        return values

    def action_save(self):
        self.ensure_one()
        self.company_id.payroll_accrued_salary_account_id = self.accrued_salary_account_id
        return {"type": "ir.actions.act_window_close"}
