"""One bell provider; no copied notifications, parallel inbox or new permissions."""
from urllib.parse import urlsplit
from odoo import api, models


class WorkspaceEPSNotifications(models.Model):
    _inherit = 'pbw.notification.seen'

    @api.model
    def _eps_bell_allowed(self, user):
        user = user.sudo()
        return bool(user.active and not user._is_public()
                    and not user.has_group('employee_portal_suite.group_attendance_only')
                    and (user.with_company(user.company_id).employee_id
                         or (not user.share and any(user.has_group('employee_portal_suite.' + role) for role in (
                             'group_employee_portal_superadmin', 'group_salary_report_viewer',
                             'group_portal_report_uploader', 'group_employee_portal_manager',
                             'group_employee_portal_hr', 'group_employee_portal_finance',
                             'group_employee_portal_ceo', 'group_mr_purchase_rep', 'group_mr_store_manager',
                             'group_mr_project_manager', 'group_mr_projects_director')))))

    @api.model
    def _can_use_bell(self, user):
        return super()._can_use_bell(user) or self._eps_bell_allowed(user)

    @api.model
    def _external_bell_items(self, user):
        items = list(super()._external_bell_items(user))
        if not self._eps_bell_allowed(user):
            return items
        # EPS keeps its own approval/read rules. Do not extend its summary with
        # PBW and then read it back: that would recurse or duplicate both feeds.
        summary = self.env['portal.report.seen'].sudo()._get_notification_summary(user.sudo())
        used_urls = set()
        for kind, value in summary.items():
            count = max(0, int(value.get('new', 0) or 0))
            url = str(value.get('url') or '')
            parsed = urlsplit(url)
            if (not count or parsed.scheme or parsed.netloc or '\\' in url
                    or any(ord(char) < 32 for char in url)
                    or not (parsed.path == '/my/employee' or parsed.path.startswith('/my/employee/'))):
                continue
            # A link returned twice by installed legacy providers is one source.
            if url in used_urls:
                continue
            used_urls.add(url)
            items.append({'key': 'eps:%s' % kind, 'source': 'eps', 'category': kind,
                          'title': value.get('label') or kind, 'body': '',
                          'count': count, 'url': url, 'date': False})
        return items
