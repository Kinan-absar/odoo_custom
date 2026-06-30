# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PortalReportSeen(models.Model):
    """Tracks, per portal user and notification type, the last time the user
    opened the corresponding list/approvals page. Used to compute "new since
    you last checked" badges on the Employee Portal dashboard cards (Salary
    Reports, Reports, ER Approvals, MR Approvals, Signatures) without
    affecting what other users see, since the underlying records are shared.
    """
    _name = 'portal.report.seen'
    _description = 'Portal Notification Last Seen Marker'
    _rec_name = 'report_type'

    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    report_type = fields.Selection([
        ('salary_report', 'Salary Reports'),
        ('portal_report', 'Reports'),
        ('er_approval', 'ER Approvals'),
        ('mr_approval', 'MR Approvals'),
        ('sign_request', 'Signatures'),
    ], required=True, index=True)
    last_seen_date = fields.Datetime(string='Last Seen At', required=True, default=fields.Datetime.now)

    _sql_constraints = [
        ('user_report_type_uniq', 'unique(user_id, report_type)',
         'A user can only have one last-seen marker per notification type.'),
    ]

    @api.model
    def _get_last_seen(self, user_id, report_type):
        """Return the datetime the given user last saw this notification type's
        page, or False if they have never opened it (callers decide how to treat
        that — usually "everything currently visible counts as new")."""
        marker = self.sudo().search([
            ('user_id', '=', user_id),
            ('report_type', '=', report_type),
        ], limit=1)
        return marker.last_seen_date if marker else False

    @api.model
    def _get_last_seen_map(self, user_id, report_types):
        """Batch version of _get_last_seen for several types at once, returning
        {report_type: last_seen_date_or_False}. Avoids one query per card when
        computing the bell's counts together."""
        markers = self.sudo().search([
            ('user_id', '=', user_id),
            ('report_type', 'in', report_types),
        ])
        result = {rt: False for rt in report_types}
        for marker in markers:
            result[marker.report_type] = marker.last_seen_date
        return result

    @api.model
    def _mark_seen(self, user_id, report_type):
        """Upsert the last-seen marker for this user/notification type to now."""
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

    # ------------------------------------------------------------------
    # Shared notification summary, used by the header bell (every portal
    # page, via the shared layout) and the dashboard cards. Centralized here
    # so the "what counts as new" rule for each type only lives in one place.
    # ------------------------------------------------------------------
    @api.model
    def _get_notification_summary(self, user):
        """Return a dict describing unseen counts per notification type for
        `user`, e.g.:
            {
                'salary_report': {'count': 2, 'new': 1, 'url': '/my/employee/salary-reports', 'label': 'Salary Reports'},
                'portal_report': {...},
                'er_approval': {...},
                'mr_approval': {...},
                'sign_request': {...},
            }
        Types the user has no access to are omitted entirely. Only types with
        new > 0 need to be shown by the caller, but totals are included too
        in case a caller wants them.
        """
        env = self.env
        types = ['salary_report', 'portal_report', 'er_approval', 'mr_approval', 'sign_request']
        last_seen_map = self._get_last_seen_map(user.id, types)
        summary = {}
        employee = user.employee_id

        # ---- Salary Reports (read-only portal viewer group) ----
        if user.has_group('employee_portal_suite.group_salary_report_viewer'):
            domain = [('state', 'in', ['generated', 'batch_created'])]
            Report = env['employee.attendance.salary.report'].sudo()
            total = Report.search_count(domain)
            new = self._count_new(Report, domain, last_seen_map.get('salary_report'))
            summary['salary_report'] = {
                'count': total, 'new': new,
                'url': '/my/employee/salary-reports', 'label': 'Salary Reports',
            }

        # ---- Portal Reports (visible by user's portal groups) ----
        domain = [
            ('active', '=', True),
            ('allowed_group_ids', 'in', user.groups_id.ids),
        ]
        Report = env['portal.report.document'].sudo()
        total = Report.search_count(domain)
        if total:
            new = self._count_new(Report, domain, last_seen_map.get('portal_report'))
            summary['portal_report'] = {
                'count': total, 'new': new,
                'url': '/my/employee/reports', 'label': 'Reports',
            }

        # ---- ER Approvals: pending list is per-user/state, not a clean domain ----
        if (
            user.has_group('employee_portal_suite.group_employee_portal_manager')
            or user.has_group('employee_portal_suite.group_employee_portal_hr')
            or user.has_group('employee_portal_suite.group_employee_portal_finance')
            or user.has_group('employee_portal_suite.group_employee_portal_ceo')
        ):
            EmployeeRequest = env['employee.request'].sudo()
            pending = EmployeeRequest.search([('state', 'in', ['manager', 'hr', 'finance', 'ceo'])])
            pending_for_user = pending.filtered(lambda rec: (
                (rec.state == 'manager' and user.has_group('employee_portal_suite.group_employee_portal_manager') and rec.manager_id == employee)
                or (rec.state == 'hr' and user.has_group('employee_portal_suite.group_employee_portal_hr'))
                or (rec.state == 'finance' and user.has_group('employee_portal_suite.group_employee_portal_finance'))
                or (rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'))
            ))
            last_seen = last_seen_map.get('er_approval')
            new = len(pending_for_user) if not last_seen else len(pending_for_user.filtered(lambda r: r.write_date > last_seen))
            summary['er_approval'] = {
                'count': len(pending_for_user), 'new': new,
                'url': '/my/employee/approvals', 'label': 'ER Approvals',
            }

        # ---- MR Approvals: same shape as ER Approvals ----
        if (
            user.has_group('employee_portal_suite.group_mr_purchase_rep')
            or user.has_group('employee_portal_suite.group_mr_store_manager')
            or user.has_group('employee_portal_suite.group_mr_project_manager')
            or user.has_group('employee_portal_suite.group_mr_projects_director')
            or user.has_group('employee_portal_suite.group_employee_portal_ceo')
        ):
            Material = env['material.request'].sudo()
            pending = Material.search([('state', 'in', ['purchase', 'store', 'project_manager', 'director', 'ceo'])])
            pending_for_user = pending.filtered(lambda rec: (
                (rec.state == 'purchase' and user.has_group('employee_portal_suite.group_mr_purchase_rep'))
                or (rec.state == 'store' and rec.store_manager_user_id == user)
                or (rec.state == 'project_manager' and rec.project_manager_user_id == user)
                or (rec.state == 'director' and user.has_group('employee_portal_suite.group_mr_projects_director'))
                or (rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'))
            ))
            last_seen = last_seen_map.get('mr_approval')
            new = len(pending_for_user) if not last_seen else len(pending_for_user.filtered(lambda r: r.write_date > last_seen))
            summary['mr_approval'] = {
                'count': len(pending_for_user), 'new': new,
                'url': '/my/employee/material/approvals', 'label': 'MR Approvals',
            }

        # ---- Signatures (sign.request.item, only if 'sign' module installed) ----
        if 'sign.request.item' in env:
            SignItem = env['sign.request.item'].sudo()
            domain = [('partner_id', '=', user.partner_id.id), ('state', '=', 'sent')]
            total = SignItem.search_count(domain)
            if total:
                new = self._count_new(SignItem, domain, last_seen_map.get('sign_request'))
                summary['sign_request'] = {
                    'count': total, 'new': new,
                    'url': '/my/employee/sign', 'label': 'Signatures',
                }

        return summary

    @api.model
    def _count_new(self, Model, domain, last_seen):
        """Count records matching `domain` created after `last_seen`. If the
        user has never seen this type before (`last_seen` is False), everything
        currently visible counts as new."""
        if not last_seen:
            return Model.search_count(domain)
        return Model.search_count(domain + [('create_date', '>', last_seen)])

