# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PortalReportSeen(models.Model):
    """Tracks, per portal user and report type, the last time the user opened
    the corresponding list page. Used to compute a "new reports" badge on the
    Employee Portal dashboard cards (Salary Reports / Reports) without
    affecting what other users see, since reports are shared records.
    """
    _name = 'portal.report.seen'
    _description = 'Portal Report Last Seen Marker'
    _rec_name = 'report_type'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    report_type = fields.Selection([
        ('salary_report', 'Salary Reports'),
        ('portal_report', 'Reports'),
    ], required=True, index=True)
    last_seen_date = fields.Datetime(string='Last Seen At', required=True, default=fields.Datetime.now)

    _sql_constraints = [
        ('user_report_type_uniq', 'unique(user_id, report_type)',
         'A user can only have one last-seen marker per report type.'),
    ]

    @api.model
    def _get_last_seen(self, user_id, report_type):
        """Return the datetime the given user last saw this report type's list,
        or False if they have never opened it (treat everything as new in that case
        is too noisy on first login, so callers should fall back to "now" semantics
        as appropriate)."""
        marker = self.sudo().search([
            ('user_id', '=', user_id),
            ('report_type', '=', report_type),
        ], limit=1)
        return marker.last_seen_date if marker else False

    @api.model
    def _mark_seen(self, user_id, report_type):
        """Upsert the last-seen marker for this user/report type to now."""
        marker = self.sudo().search([
            ('user_id', '=', user_id),
            ('report_type', '=', report_type),
        ], limit=1)
        now = fields.Datetime.now()
        if marker:
            marker.write({'last_seen_date': now})
        else:
            self.sudo().create({
                'user_id': user_id,
                'report_type': report_type,
                'last_seen_date': now,
            })
        return now
