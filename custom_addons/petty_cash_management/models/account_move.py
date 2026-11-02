from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    petty_cash_report_id = fields.Many2one(
        'petty.cash', string='Petty Cash Report',
        compute='_compute_petty_cash_report_id', compute_sudo=False,
    )

    @api.depends_context('uid', 'company')
    def _compute_petty_cash_report_id(self):
        # Resolve the existing source link, including vouchers created before upgrade.
        for move in self:
            move.petty_cash_report_id = False
        reports = self.env['petty.cash']
        if self.ids and reports.check_access_rights('read', raise_exception=False):
            sources = reports.search([('journal_entry_id', 'in', self.ids)], order='id')
            by_move = {}
            for report in sources:
                by_move.setdefault(report.journal_entry_id.id, report)
            for move in self:
                move.petty_cash_report_id = by_move.get(move.id, False)
