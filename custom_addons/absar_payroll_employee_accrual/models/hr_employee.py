from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _get_payroll_account_partner(self):
        """Return the employee's existing linked contact/partner.

        ABSAR employees already have partners, so there is intentionally no
        extra payroll-specific partner field on the employee form.
        """
        self.ensure_one()

        # Keep this compatible with slightly different employee layouts and
        # localizations across Odoo Enterprise databases.
        for field_name in ("work_contact_id", "user_partner_id", "address_home_id", "private_address_id"):
            if field_name in self._fields:
                partner = self[field_name]
                if partner and getattr(partner, "_name", None) == "res.partner":
                    return partner

        if "user_id" in self._fields and self.user_id and self.user_id.partner_id:
            return self.user_id.partner_id

        return self.env["res.partner"]
