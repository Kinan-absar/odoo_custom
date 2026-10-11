from odoo import models


def distribution_account_ids(distribution):
    return {
        int(token)
        for key in (distribution or {})
        for token in str(key).split(',')
        if token.strip().isdigit() and int(token) > 0
    }


def format_distribution(distribution, names):
    labels = []
    for key, percentage in (distribution or {}).items():
        accounts = [names[int(token)] for token in str(key).split(',')
                    if token.strip().isdigit() and int(token) in names]
        if accounts:
            labels.append('%s (%g%%)' % (' / '.join(accounts), float(percentage)))
    return '\n'.join(labels)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _absar_jv_analytic_labels(self):
        self.ensure_one()
        account_ids = set()
        for line in self.line_ids:
            account_ids.update(distribution_account_ids(line.analytic_distribution))
        accounts = self.env['account.analytic.account'].browse(sorted(account_ids)).exists()
        names = {account.id: account.name for account in accounts}
        return {line.id: format_distribution(line.analytic_distribution, names)
                for line in self.line_ids}
