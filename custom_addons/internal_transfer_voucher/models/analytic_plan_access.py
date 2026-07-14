from odoo import models


class AccountAnalyticPlan(models.Model):
    _inherit = "account.analytic.plan"

    def _column_name(self):
        """Resolve the root plan with read-only elevated access.

        Odoo computes analytic distributions from purchase, sale, and journal
        lines for ordinary users. A user may be allowed to use a child plan
        while the root plan is hidden by company/access rules. In that case,
        ``self.root_id`` becomes an empty recordset and standard Odoo crashes
        with ``Expected singleton: account.analytic.plan()``.

        Only the root-plan metadata lookup is elevated. No analytic plan,
        distribution, accounting entry, or business record is written.
        """
        self.ensure_one()
        root = self.sudo().root_id
        if root:
            return root._strict_column_name()
        # Keep Odoo's standard behavior for genuinely malformed data.
        return super()._column_name()
