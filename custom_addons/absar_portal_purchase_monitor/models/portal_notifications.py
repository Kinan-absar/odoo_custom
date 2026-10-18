from odoo import api, fields, models, _

PREFIX = 'absar_portal_purchase_monitor.'


class PurchasePortalNotifications(models.Model):
    _inherit = 'portal.report.seen'

    report_type = fields.Selection(
        selection_add=[('purchase_approval', 'Purchase Approvals')],
        ondelete={'purchase_approval': 'cascade'})

    @api.model
    def _get_purchase_approval_summary(self, user):
        """Persistent portal attention, scoped exactly like the approval queue."""
        user = user.sudo()
        if (not user.active or not user.has_group(PREFIX + 'group_portal_purchase_approver') or
                user.has_group('employee_portal_suite.group_attendance_only') or
                (user.share and not user.with_company(user.company_id).employee_id)):
            return {}
        domain = [('company_id', 'in', user.company_ids.ids),
                  ('absar_portal_preparer_id', '!=', False),
                  ('absar_portal_preparer_id', '!=', user.id),
                  ('absar_portal_review_state', '=', 'submitted'),
                  ('state', 'in', ['draft', 'sent'])]
        orders = self.env['purchase.order'].sudo()
        count = orders.search_count(domain)
        seen = self._get_last_seen(user.id, 'purchase_approval')
        unseen = orders.search_count(domain + [('write_date', '>', seen)]) if seen else count
        return {'count': count, 'new': unseen,
                'url': '/my/employee/purchase/approvals', 'label': _('Purchase Approvals')}

    @api.model
    def _get_notification_summary(self, user):
        summary = super()._get_notification_summary(user)
        purchase = self._get_purchase_approval_summary(user)
        if purchase:
            summary['purchase_approval'] = purchase
        return summary
