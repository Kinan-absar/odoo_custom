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
        """Place the addon entry directly in Payroll > Configuration.

        Use the exact standard Payroll Settings menu as an anchor, then attach
        our menu to the same parent. This avoids guessing the XML ID of the
        Configuration parent menu and works with the menu structure used by
        this Odoo 18 database.
        """
        Menu = self.env["ir.ui.menu"].sudo()

        settings_menu = self.env.ref(
            "hr_payroll.menu_hr_payroll_global_settings",
            raise_if_not_found=False,
        )
        if not settings_menu or not settings_menu.parent_id:
            return True

        parent_menu = settings_menu.parent_id

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
            # Settings is sequence 0 in this database; put ours immediately after it.
            "sequence": 1,
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
