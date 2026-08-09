from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SharePointHistoricalArchiveWizard(models.TransientModel):
    _name = 'sharepoint.historical.archive.wizard'
    _description = 'Queue Historical Accounting Documents for SharePoint Archive'

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
    document_type = fields.Selection([
        ('all', 'All Enabled Document Types'),
        ('entry', 'Journal Vouchers / Journal Entries'),
        ('in_invoice', 'Vendor Bills'),
        ('in_refund', 'Vendor Credit Notes'),
        ('out_invoice', 'Customer Invoices'),
        ('out_refund', 'Customer Credit Notes'),
    ], string='Document Type', required=True, default='all')
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

    def _enabled_move_types(self, config):
        move_types = []
        if config.archive_entries:
            move_types.append('entry')
        if config.archive_vendor_bills:
            move_types.extend(['in_invoice', 'in_refund'])
        if config.archive_customer_invoices:
            move_types.extend(['out_invoice', 'out_refund'])
        return move_types

    def action_queue_archive(self):
        self.ensure_one()

        config = self.env['sharepoint.archive.config']._get_for_company(self.company_id)
        if not config:
            raise UserError(_('No active SharePoint archive configuration exists for %s.') % self.company_id.display_name)

        enabled_types = self._enabled_move_types(config)
        if not enabled_types:
            raise UserError(_('No accounting document types are enabled in the SharePoint archive configuration.'))

        if self.document_type == 'all':
            requested_types = enabled_types
        else:
            requested_types = [self.document_type]
            if self.document_type not in enabled_types:
                label = dict(self._fields['document_type'].selection).get(self.document_type, self.document_type)
                raise UserError(_('%s is disabled in the SharePoint archive configuration.') % label)

        domain = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'posted'),
            ('move_type', 'in', requested_types),
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

        counts = {
            'entry': len(moves.filtered(lambda m: m.move_type == 'entry')),
            'in_invoice': len(moves.filtered(lambda m: m.move_type == 'in_invoice')),
            'in_refund': len(moves.filtered(lambda m: m.move_type == 'in_refund')),
            'out_invoice': len(moves.filtered(lambda m: m.move_type == 'out_invoice')),
            'out_refund': len(moves.filtered(lambda m: m.move_type == 'out_refund')),
        }
        message = _(
            '%(queued)s document(s) queued for SharePoint. %(archived)s already archived and skipped. '
            '%(total)s posted document(s) matched.\n'
            'JVs: %(entries)s | Vendor Bills: %(vendor_bills)s | Vendor Credit Notes: %(vendor_refunds)s | '
            'Customer Invoices: %(customer_invoices)s | Customer Credit Notes: %(customer_refunds)s'
        ) % {
            'queued': len(to_queue),
            'archived': len(already_archived),
            'total': len(moves),
            'entries': counts['entry'],
            'vendor_bills': counts['in_invoice'],
            'vendor_refunds': counts['in_refund'],
            'customer_invoices': counts['out_invoice'],
            'customer_refunds': counts['out_refund'],
        }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Historical Accounting Archive'),
                'message': message,
                'type': 'success' if to_queue else 'warning',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
