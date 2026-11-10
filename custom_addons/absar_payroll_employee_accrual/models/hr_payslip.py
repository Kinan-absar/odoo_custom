from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_payslip_done(self):
        """Let standard Odoo build the payroll move, then rewrite only the configured
        accrued-salary account into one line per employee partner.

        With 'Batch Account Move Lines' enabled, standard Odoo keeps one move but
        anonymizes the liability. This hook preserves the single move while restoring
        employee detail only on the accrued salary account.
        """
        res = super().action_payslip_done()

        # hr_payroll_account supplies move_id. Keep a defensive check so the addon
        # fails clearly if another customization changes the payroll accounting model.
        if "move_id" not in self._fields:
            raise UserError(_(
                "ABSAR Payroll Employee Accrual Split could not find the payroll move field (move_id). "
                "Please check compatibility with the installed payroll accounting customization."
            ))

        for move in self.mapped("move_id").filtered(lambda m: m):
            self._absar_split_accrued_salary_move(move)

        return res

    def _absar_split_accrued_salary_move(self, move):
        company = move.company_id
        target_account = company.payroll_accrued_salary_account_id
        if not target_account:
            return

        if move.state != "draft":
            raise UserError(_(
                "Payroll journal entry %s is already posted. Employee accrual splitting "
                "must be applied while the payroll entry is still in Draft."
            ) % move.display_name)

        # Get every payslip attached to this move, not only the recordset that happened
        # to trigger the hook. This is important when Odoo batches a whole period.
        slips = self.search([
            ("move_id", "=", move.id),
            ("company_id", "=", company.id),
        ])
        if not slips:
            return

        currency = company.currency_id
        employee_amounts = defaultdict(float)
        employee_records = {}

        for slip in slips:
            employee = slip.employee_id
            partner = employee._get_payroll_account_partner()
            if not partner:
                raise UserError(_(
                    "Employee '%s' has no Payroll Accounting Partner (and no usable linked contact). "
                    "Open the employee and set Payroll Accounting Partner before confirming payroll."
                ) % employee.display_name)

            employee_records[employee.id] = (employee, partner)

            for line in slip.line_ids:
                rule = line.salary_rule_id
                if not rule:
                    continue

                amount = line.total
                if currency.is_zero(amount):
                    continue

                # Signed contribution to the target liability account:
                #   credit account -> +amount
                #   debit account  -> -amount
                # Negative salary-rule totals naturally reverse the side.
                if getattr(rule, "account_credit", False) == target_account:
                    employee_amounts[employee.id] += amount
                if getattr(rule, "account_debit", False) == target_account:
                    employee_amounts[employee.id] -= amount

        # Compare our reconstructed payroll amount with what standard Odoo created
        # before touching the move. This prevents silently changing accounting totals
        # if another custom payroll module uses different accounting logic.
        existing_target_lines = move.line_ids.filtered(lambda l: l.account_id == target_account)
        if not existing_target_lines:
            return

        existing_net_credit = sum(existing_target_lines.mapped("credit")) - sum(existing_target_lines.mapped("debit"))
        computed_net_credit = sum(employee_amounts.values())

        if not currency.is_zero(existing_net_credit - computed_net_credit):
            raise UserError(_(
                "The accrued salary split was NOT applied because the computed employee total does not "
                "match Odoo's existing payroll accounting total.\n\n"
                "Account: %(account)s\n"
                "Odoo net credit: %(odoo)s\n"
                "Computed employee net credit: %(computed)s\n\n"
                "This safety check usually means another payroll customization/localization changes the "
                "accounting logic. No journal lines were modified."
            ) % {
                "account": target_account.display_name,
                "odoo": currency.format(existing_net_credit),
                "computed": currency.format(computed_net_credit),
            })

        # Replace only the configured accrued-salary account lines. Expense lines and
        # every other payroll account remain exactly as standard Odoo generated them.
        existing_target_lines.with_context(check_move_validity=False).unlink()

        vals_list = []
        for employee_id, signed_credit in employee_amounts.items():
            signed_credit = currency.round(signed_credit)
            if currency.is_zero(signed_credit):
                continue

            employee, partner = employee_records[employee_id]
            vals_list.append({
                "move_id": move.id,
                "account_id": target_account.id,
                "partner_id": partner.id,
                "name": _("Accrued Salary - %s") % employee.display_name,
                "debit": abs(signed_credit) if signed_credit < 0 else 0.0,
                "credit": signed_credit if signed_credit > 0 else 0.0,
            })

        if vals_list:
            self.env["account.move.line"].with_context(check_move_validity=False).create(vals_list)

        # Final accounting safety check.
        balance = sum(move.line_ids.mapped("debit")) - sum(move.line_ids.mapped("credit"))
        if not currency.is_zero(balance):
            raise UserError(_(
                "The payroll journal entry became unbalanced after employee accrual splitting. "
                "Please cancel this operation and contact your Odoo administrator. Difference: %s"
            ) % currency.format(balance))
