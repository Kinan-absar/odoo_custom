# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AbsarSalesBellEvent(models.Model):
    _name = 'absar.sales.bell.event'
    _description = 'Sales review notification per recipient'
    _order = 'create_date desc, id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    event_type = fields.Selection([('submitted', 'Approval requested'), ('approved', 'Approved'), ('returned', 'Returned')], required=True)
    title = fields.Char(required=True)
    is_read = fields.Boolean(default=False, index=True)
    company_id = fields.Many2one('res.company', related='order_id.company_id', store=True)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def write(self, vals):
        tracking = 'absar_portal_review_state' in vals
        before = {rec.id: rec.absar_portal_review_state for rec in self} if tracking else {}
        result = super().write(vals)
        if tracking and not self.env.context.get('absar_bell_suppress'):
            for order in self:
                state = order.absar_portal_review_state
                if before.get(order.id) == state or state not in ('submitted', 'approved', 'returned') or not order.absar_portal_creator_id:
                    continue
                Event = self.env['absar.sales.bell.event'].sudo()
                if state == 'submitted':
                    group = self.env.ref('absar_portal_sales.group_portal_sales_approver', raise_if_not_found=False)
                    recipients = group.sudo().users.filtered(lambda u: u.active and u.id != order.absar_portal_creator_id.id and order.company_id in u.company_ids) if group else self.env['res.users']
                    title = _('Quotation %s requires your approval') % order.name
                else:
                    recipients = order.absar_portal_creator_id if order.absar_portal_creator_id.active else self.env['res.users']
                    title = (_('Quotation %s approved') if state == 'approved' else _('Quotation %s returned for correction')) % order.name
                for recipient in recipients:
                    Event.create({'user_id': recipient.id, 'order_id': order.id, 'event_type': state, 'title': title})
        return result


class PortalReportSeen(models.Model):
    _inherit = 'portal.report.seen'

    @api.model
    def _get_notification_summary(self, user):
        summary = super()._get_notification_summary(user)
        if user.has_group('absar_portal_sales.group_portal_sales_creator') or user.has_group('absar_portal_sales.group_portal_sales_approver'):
            Event = self.env['absar.sales.bell.event'].sudo()
            domain = [('user_id', '=', user.id), ('company_id', 'in', user.company_ids.ids)]
            unread = Event.search_count(domain + [('is_read', '=', False)])
            if unread:
                summary['sales_review'] = {'count': Event.search_count(domain), 'new': unread,
                    'url': '/my/employee/sales/notifications', 'label': _('Sales Approvals & Decisions')}
        return summary
