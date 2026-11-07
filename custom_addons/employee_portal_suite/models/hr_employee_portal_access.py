# -*- coding: utf-8 -*-
from odoo import api, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model
    def _employee_portal_base_groups(self):
        """Technical baseline groups automatically tied to Employee -> Related User.

        These groups are intentionally not exposed as configurable business roles.
        Functional roles (Manager, HR, Finance, MR approvers, etc.) stay manual.
        """
        return self.env["res.groups"].sudo().browse([
            self.env.ref("employee_portal_suite.group_employee_portal").id,
            self.env.ref("employee_portal_suite.group_employee_portal_employee").id,
        ])

    def _ensure_employee_portal_base_access(self):
        groups = self._employee_portal_base_groups()
        users = self.mapped("user_id").sudo().filtered(lambda u: u.active)
        for user in users:
            missing = groups - user.groups_id
            if missing:
                user.write({"groups_id": [(4, group.id) for group in missing]})
        return True

    @api.model
    def _cleanup_employee_portal_base_access(self, users):
        """Remove technical baseline groups when a user is no longer linked to any employee."""
        users = users.sudo().filtered(lambda u: u.exists())
        if not users:
            return True
        groups = self._employee_portal_base_groups()
        Employee = self.sudo().with_context(active_test=False)
        for user in users:
            if not Employee.search_count([("user_id", "=", user.id)], limit=1):
                present = groups & user.groups_id
                if present:
                    user.write({"groups_id": [(3, group.id) for group in present]})
        return True

    @api.model
    def _sync_all_employee_portal_base_groups(self):
        """Upgrade/install synchronizer for existing Employee -> Related User links."""
        employees = self.sudo().with_context(active_test=False).search([("user_id", "!=", False)])
        employees._ensure_employee_portal_base_access()

        groups = self._employee_portal_base_groups()
        grouped_users = groups.mapped("users")
        linked_user_ids = set(employees.mapped("user_id").ids)
        stale_users = grouped_users.filtered(lambda u: u.id not in linked_user_ids)
        self._cleanup_employee_portal_base_access(stale_users)
        return True

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_employee_portal_base_access()
        return records

    def write(self, vals):
        old_users = self.mapped("user_id") if "user_id" in vals else self.env["res.users"]
        result = super().write(vals)
        if "user_id" in vals:
            self._ensure_employee_portal_base_access()
            self._cleanup_employee_portal_base_access(old_users - self.mapped("user_id"))
        return result

    def unlink(self):
        old_users = self.mapped("user_id")
        result = super().unlink()
        self._cleanup_employee_portal_base_access(old_users)
        return result
