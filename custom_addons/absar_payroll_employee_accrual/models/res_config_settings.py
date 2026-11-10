from odoo import api, fields, models


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

    @api.model
    def _absar_ensure_payroll_config_menu(self):
        """Place the addon entry directly inside Payroll > Configuration.

        Odoo versions/localizations can use different XML IDs for the
        Configuration menu itself. The Payroll root XML ID is stable, so we
        resolve that root first and then locate its direct child named
        Configuration. This avoids creating the entry in Settings/HR by mistake.
        """
        Menu = self.env["ir.ui.menu"].sudo().with_context(lang="en_US")

        payroll_root = self.env.ref(
            "hr_payroll.menu_hr_payroll_root", raise_if_not_found=False
        )

        parent_menu = Menu.browse()
        if payroll_root:
            # Configuration is a direct top-menu child of the Payroll app.
            parent_menu = Menu.search([
                ("parent_id", "=", payroll_root.id),
                ("name", "=", "Configuration"),
            ], limit=1)

            # Fallback for renamed/translatable menu labels: use the direct child
            # that contains the standard Payroll Settings entry.
            if not parent_menu:
                for child in Menu.search([("parent_id", "=", payroll_root.id)]):
                    descendants = Menu.search([("parent_id", "=", child.id)])
                    if any((m.name or "").strip().lower() == "settings" for m in descendants):
                        parent_menu = child
                        break

        if not parent_menu:
            # Do not put it somewhere unrelated. If Payroll Configuration cannot
            # be identified, leave the menu untouched instead of falling back to
            # the global Settings app.
            return True

        action = self.env.ref(
            "absar_payroll_employee_accrual.action_absar_payroll_accrual_settings",
            raise_if_not_found=False,
        )
        if not action:
            return True

        menu_xmlid = "absar_payroll_employee_accrual.menu_absar_payroll_accrual_settings"
        menu = self.env.ref(menu_xmlid, raise_if_not_found=False)
        vals = {
            "name": "Employee Accrued Salary",
            "parent_id": parent_menu.id,
            "action": "ir.actions.act_window,%s" % action.id,
            "sequence": 5,
        }

        if menu:
            menu.sudo().write(vals)
        else:
            menu = Menu.create(vals)
            self.env["ir.model.data"].sudo().create({
                "module": "absar_payroll_employee_accrual",
                "name": "menu_absar_payroll_accrual_settings",
                "model": "ir.ui.menu",
                "res_id": menu.id,
                "noupdate": False,
            })

        return True
