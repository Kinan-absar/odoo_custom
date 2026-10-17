# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AbsarPortalSalesBellEvent(models.Model):
    """Persistent per-recipient Sales notification for the existing EPS bell."""
    _name = 'absar.portal.sales.bell.event'
    _description = 'Sales Portal Bell Notification'
    _order = 'create_date desc, id desc'

    recipient_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    category = fields.Selection([
        ('sales_approval', 'Sales Approvals'),
        ('sales_decision', 'Sales Review Decisions'),
    ], required=True, index=True)
    event_type = fields.Selection([
        ('submitted', 'Submitted'), ('approved', 'Approved'), ('returned', 'Returned')
    ], required=True)
    note = fields.Char()


class PortalReportSeenSales(models.Model):
    _inherit = 'portal.report.seen'

    report_type = fields.Selection(selection_add=[
        ('sales_approval', 'Sales Approvals'),
        ('sales_decision', 'Sales Review Decisions'),
    ], ondelete={'sales_approval': 'cascade', 'sales_decision': 'cascade'})

    @api.model
    def _get_notification_summary(self, user):
        summary = super()._get_notification_summary(user)
        Events = self.env['absar.portal.sales.bell.event'].sudo()
        categories = []
        if user.has_group('absar_portal_sales.group_portal_sales_approver'):
            categories.append(('sales_approval', 'Sales Approvals', '/my/employee/sales/approvals'))
        if user.has_group('absar_portal_sales.group_portal_sales_creator'):
            categories.append(('sales_decision', 'Sales Review Decisions', '/my/employee/sales'))
        for key, label, url in categories:
            domain = [('recipient_id', '=', user.id), ('category', '=', key),
                      ('order_id.company_id', 'in', user.company_ids.ids)]
            # Approval alerts only remain actionable while the offer awaits review.
            if key == 'sales_approval':
                domain += [('order_id.absar_portal_review_state', '=', 'submitted'),
                           ('order_id.state', '=', 'draft'),
                           ('order_id.absar_portal_creator_id', '!=', user.id)]
            last_seen = self._get_last_seen(user.id, key)
            summary[key] = {
                'count': Events.search_count(domain),
                'new': Events.search_count(domain + ([('create_date', '>', last_seen)] if last_seen else [])),
                'url': url, 'label': label,
            }
        return summary
