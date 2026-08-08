import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sharepoint_archive_state = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('archived', 'Archived'),
        ('failed', 'Failed'),
    ], string='SharePoint Archive', default='not_required', copy=False, index=True, readonly=True)
    sharepoint_archived_at = fields.Datetime(copy=False, readonly=True)
    sharepoint_web_url = fields.Char(copy=False, readonly=True)
    sharepoint_error = fields.Text(copy=False, readonly=True)
    sharepoint_attempts = fields.Integer(copy=False, readonly=True, default=0)

    def action_post(self):
        result = super().action_post()
        self._sharepoint_mark_for_archive()
        return result

    def button_draft(self):
        result = super().button_draft()
        self.filtered(lambda m: m.sharepoint_archive_state != 'archived').write({
            'sharepoint_archive_state': 'not_required',
            'sharepoint_error': False,
        })
        return result

    def _sharepoint_mark_for_archive(self):
        for move in self.filtered(lambda m: m.state == 'posted'):
            config = self.env['sharepoint.archive.config']._get_for_company(move.company_id)
            if config and config.auto_archive and config._move_is_enabled(move):
                move.write({
                    'sharepoint_archive_state': 'pending',
                    'sharepoint_error': False,
                })

    def action_sharepoint_archive_now(self):
        for move in self:
            if move.state != 'posted':
                raise UserError(_('Only posted accounting entries can be archived.'))
            config = self.env['sharepoint.archive.config']._get_for_company(move.company_id)
            if not config:
                raise UserError(_('No active SharePoint archive configuration exists for %s.') % move.company_id.display_name)
            move.write({'sharepoint_archive_state': 'pending', 'sharepoint_error': False})
            move._sharepoint_archive_one(config, raise_errors=True)
        return True

    def action_sharepoint_retry(self):
        self.filtered(lambda m: m.state == 'posted').write({
            'sharepoint_archive_state': 'pending',
            'sharepoint_error': False,
        })
        return True

    @api.model
    def _cron_sharepoint_archive(self, limit=20):
        moves = self.search([
            ('state', '=', 'posted'),
            ('sharepoint_archive_state', 'in', ['pending', 'failed']),
        ], order='date asc, id asc', limit=limit)
        done = 0
        for move in moves:
            config = self.env['sharepoint.archive.config']._get_for_company(move.company_id)
            if not config or not config._move_is_enabled(move):
                move.write({'sharepoint_archive_state': 'not_required'})
                done += 1
                continue
            move._sharepoint_archive_one(config, raise_errors=False)
            done += 1
        remaining = self.search_count([
            ('state', '=', 'posted'),
            ('sharepoint_archive_state', 'in', ['pending', 'failed']),
        ])
        cron = self.env['ir.cron']
        if hasattr(cron, '_notify_progress'):
            cron._notify_progress(done=done, remaining=remaining)
        return True

    def _sharepoint_folder_path(self, config):
        self.ensure_one()
        move_date = self.date or fields.Date.context_today(self)
        month_folder = '%02d - %s' % (move_date.month, move_date.strftime('%B'))
        reference = self.name if self.name and self.name != '/' else 'MOVE-%s' % self.id
        return '/'.join([
            config.root_folder,
            str(move_date.year),
            month_folder,
            config._document_type_folder(self),
            config._safe_name(reference),
        ])

    def action_sharepoint_unarchive(self):
        for move in self:
            if move.sharepoint_archive_state != 'archived':
                raise UserError(_('Only entries already archived to SharePoint can be unarchived.'))
            config = self.env['sharepoint.archive.config']._get_for_company(move.company_id)
            if not config:
                raise UserError(_('No active SharePoint archive configuration exists for %s.') % move.company_id.display_name)
            folder_path = move._sharepoint_folder_path(config)
            try:
                deleted = config._delete_item_by_path(folder_path)
                if not deleted:
                    raise UserError(_('The SharePoint archive folder was not found: %s') % folder_path)
                move.write({
                    'sharepoint_archive_state': 'not_required',
                    'sharepoint_archived_at': False,
                    'sharepoint_web_url': False,
                    'sharepoint_error': False,
                })
                move.message_post(body=_('Removed from SharePoint archive: %s') % folder_path)
            except Exception as exc:
                _logger.exception('SharePoint unarchive failed for account.move %s', move.id)
                if isinstance(exc, UserError):
                    raise
                raise UserError(_('SharePoint unarchive failed: %s') % exc) from exc
        return True

    def _sharepoint_archive_one(self, config, raise_errors=False):
        self.ensure_one()
        self.write({'sharepoint_attempts': self.sharepoint_attempts + 1})
        try:
            reference = self.name if self.name and self.name != '/' else 'MOVE-%s' % self.id
            folder_path = self._sharepoint_folder_path(config)
            folder = config._ensure_folder_path(folder_path)

            pdf_bytes = self._sharepoint_render_archive_pdf()
            config._upload_bytes(
                folder['id'],
                '%s.pdf' % config._safe_name(reference),
                pdf_bytes,
                'application/pdf',
            )

            if config.include_attachments:
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'account.move'),
                    ('res_id', '=', self.id),
                    ('type', '=', 'binary'),
                ])
                used_names = set()
                for attachment in attachments:
                    if not attachment.datas:
                        continue
                    filename = config._safe_name(attachment.name or ('Attachment-%s' % attachment.id))
                    filename = self._sharepoint_unique_filename(filename, used_names, attachment.id)
                    content = base64.b64decode(attachment.datas)
                    config._upload_bytes(folder['id'], filename, content, attachment.mimetype)

            self.write({
                'sharepoint_archive_state': 'archived',
                'sharepoint_archived_at': fields.Datetime.now(),
                'sharepoint_web_url': folder.get('webUrl'),
                'sharepoint_error': False,
            })
            self.message_post(body=_('Archived to SharePoint: %s') % (folder.get('webUrl') or folder_path))
            return True
        except Exception as exc:
            _logger.exception('SharePoint archive failed for account.move %s', self.id)
            self.write({
                'sharepoint_archive_state': 'failed',
                'sharepoint_error': str(exc)[:4000],
            })
            if raise_errors:
                if isinstance(exc, UserError):
                    raise
                raise UserError(_('SharePoint archive failed: %s') % exc) from exc
            return False

    def _sharepoint_render_archive_pdf(self):
        self.ensure_one()
        report = self.env.ref('sharepoint_account_archive.action_report_journal_voucher')
        pdf, _content_type = self.env['ir.actions.report']._render_qweb_pdf(report.report_name, res_ids=self.ids)
        return pdf

    @staticmethod
    def _sharepoint_unique_filename(filename, used_names, attachment_id):
        candidate = filename
        if candidate.lower() in used_names:
            if '.' in filename:
                stem, ext = filename.rsplit('.', 1)
                candidate = '%s-%s.%s' % (stem, attachment_id, ext)
            else:
                candidate = '%s-%s' % (filename, attachment_id)
        used_names.add(candidate.lower())
        return candidate
