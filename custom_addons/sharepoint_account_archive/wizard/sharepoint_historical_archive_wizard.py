from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SharePointHistoricalArchiveWizard(models.TransientModel):
    _name = 'sharepoint.historical.archive.wizard'
    _description = 'Queue Historical Journal Vouchers for SharePoint Archive'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: date(fields.Date.today().year, 1, 1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: date(fields.Date.today().year, 12, 31),
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('company_id', '=', company_id)]",
        help='Leave empty to include all journals.',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError(_('Date From must be on or before Date To.'))

    def action_queue_archive(self):
        self.ensure_one()

        config = self.env['sharepoint.archive.config']._get_for_company(self.company_id)
        if not config:
            raise UserError(_('No active SharePoint archive configuration exists for %s.') % self.company_id.display_name)
        if not config.archive_entries:
            raise UserError(_('Journal Entries / JVs are disabled in the SharePoint archive configuration.'))

        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', '=', 'entry'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.journal_id:
            domain.append(('journal_id', '=', self.journal_id.id))

        moves = self.env['account.move'].search(domain)
        already_archived = moves.filtered(lambda move: move.sharepoint_archive_state == 'archived')
        to_queue = moves - already_archived

        if to_queue:
            to_queue.write({
                'sharepoint_archive_state': 'pending',
                'sharepoint_error': False,
            })

        message = _(
            '%(queued)s journal voucher(s) queued for SharePoint. '
            '%(archived)s already archived and skipped. %(total)s posted JV(s) matched the filters.'
        ) % {
            'queued': len(to_queue),
            'archived': len(already_archived),
            'total': len(moves),
        }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Historical JV Archive'),
                'message': message,
                'type': 'success' if to_queue else 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
