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
        """Create/update the addon menu under Payroll > Configuration.

        We intentionally resolve the Payroll Configuration menu dynamically instead
        of relying on a version/localization-specific external ID. This keeps the
        addon portable across Odoo 18 Enterprise databases where that XML ID differs.
        """
        Menu = self.env["ir.ui.menu"].sudo().with_context(lang="en_US")

        def _path_names(menu):
            names = []
            current = menu
            seen = set()
            while current and current.id not in seen:
                seen.add(current.id)
                names.append((current.name or "").strip())
                current = current.parent_id
            return list(reversed(names))

        parent_menu = Menu.browse()
        # Prefer the existing Configuration menu that belongs to the Payroll app.
        for candidate in Menu.search([("name", "=", "Configuration")]):
            path = [name.lower() for name in _path_names(candidate)]
            if "payroll" in path[:-1]:
                parent_menu = candidate
                break

        # Safe fallback: HR Configuration. This should only be used if a database
        # has renamed/restructured the Payroll menus beyond recognition.
        if not parent_menu:
            parent_menu = self.env.ref("hr.menu_hr_configuration", raise_if_not_found=False)

        if not parent_menu:
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
            "sequence": 95,
        }

        if menu:
            menu.sudo().write(vals)
        else:
            menu = self.env["ir.ui.menu"].sudo().create(vals)
            self.env["ir.model.data"].sudo().create({
                "module": "absar_payroll_employee_accrual",
                "name": "menu_absar_payroll_accrual_settings",
                "model": "ir.ui.menu",
                "res_id": menu.id,
                "noupdate": False,
            })

        return True
