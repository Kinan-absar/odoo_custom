from odoo import api, models


class AccountAnalyticDistributionModel(models.Model):
    _inherit = "account.analytic.distribution.model"

    @api.model
    def _get_distribution(self, arguments):
        """Read analytic plans and distribution rules with full read access.

        Purchase, sale, and journal-line onchanges may be executed by users
        who can use an analytic plan but cannot read every related parent/root
        plan because of company or record rules. Standard Odoo then receives
        an incomplete plan recordset and crashes while resolving its technical
        analytic column.

        This method performs only the standard distribution lookup using a
        sudoed, read-only environment. It does not create, update, or delete
        analytic plans, analytic distributions, or accounting records.
        """
        return super(
            AccountAnalyticDistributionModel,
            self.sudo(),
        )._get_distribution(arguments)
