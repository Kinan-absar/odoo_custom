# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


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

    @api.model_create_multi
    def create(self, vals_list):
        """Deliver EPS Web Push for the same events already used by the bell.

        Push delivery is best-effort and must never block saving a quotation or
        creating its normal bell notification.
        """
        events = super().create(vals_list)
        push = self.env['employee.portal.webpush.service'].sudo()
        for event in events:
            try:
                recipient = event.user_id
                order = event.order_id
                if not recipient.active or not order.exists():
                    continue
                if event.event_type == 'submitted':
                    title = _('Quotation %s awaiting approval') % order.name
                    body = _('A quotation has been submitted for your review.')
                elif event.event_type == 'approved':
                    title = _('Quotation %s approved') % order.name
                    body = _('Your quotation has been approved for sending.')
                elif event.event_type == 'returned':
                    title = _('Quotation %s returned') % order.name
                    body = _('Your quotation was returned for correction.')
                else:
                    continue
                # EPS maps portal paths to /web for internal recipients. Send
                # internal approvers to the backend order; portal employees
                # to the same notification click route as the existing bell.
                path = ('/my/employee/sales/notifications/%s' % event.id
                        if recipient.share else
                        '/web#id=%s&model=sale.order&view_type=form' % order.id)
                push.send_to_user(
                    recipient, title, body, path=path,
                    kind='portal', tag='absar-sales-review-%s' % event.id,
                )
            except Exception:
                _logger.exception('Sales review web push failed for event %s', event.id)
        return events


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
