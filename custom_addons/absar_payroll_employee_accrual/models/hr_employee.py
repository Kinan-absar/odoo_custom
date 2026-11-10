from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    payroll_account_partner_id = fields.Many2one(
        "res.partner",
        string="Payroll Accounting Partner",
        help=(
            "Partner used on this employee's Accrued Salaries journal line. "
            "If empty, the module will try the employee's work contact, user partner, "
            "then private/home address partner."
        ),
    )

    def _get_payroll_account_partner(self):
        self.ensure_one()
        if self.payroll_account_partner_id:
            return self.payroll_account_partner_id

        # Keep this compatible with different Odoo employee field layouts/localizations.
        for field_name in ("work_contact_id", "user_partner_id", "address_home_id", "private_address_id"):
            if field_name in self._fields:
                partner = self[field_name]
                if partner and getattr(partner, "_name", None) == "res.partner":
                    return partner

        if "user_id" in self._fields and self.user_id and self.user_id.partner_id:
            return self.user_id.partner_id

        return self.env["res.partner"]
