from odoo import api, models
from odoo.osv import expression


def _card_counts(records, domains, base_domain):
    # The current user's access rules and active companies apply to every count.
    return [records.search_count(expression.AND([base_domain or [], domain or []]))
            for domain in domains]


class BackendCardCounts0(models.Model):
    _inherit = 'material.request'

    @api.model
    def get_backend_card_counts(self, domains, base_domain=None):
        return _card_counts(self, domains, base_domain)


class BackendCardCounts1(models.Model):
    _inherit = 'employee.request'

    @api.model
    def get_backend_card_counts(self, domains, base_domain=None):
        return _card_counts(self, domains, base_domain)
