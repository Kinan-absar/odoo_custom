# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound


class SalesBellController(http.Controller):
    @http.route('/my/employee/sales/notifications', type='http', auth='user', website=True)
    def notifications(self, **kwargs):
        user = request.env.user
        if not (user.has_group('absar_portal_sales.group_portal_sales_creator') or user.has_group('absar_portal_sales.group_portal_sales_approver')):
            raise Forbidden()
        events = request.env['absar.sales.bell.event'].sudo().search([
            ('user_id', '=', user.id), ('company_id', 'in', user.company_ids.ids)], limit=100)
        return request.render('absar_portal_sales_bell_bridge.sales_bell_inbox', {'events': events})

    @http.route('/my/employee/sales/notifications/<int:event_id>', type='http', auth='user', website=True)
    def open_notification(self, event_id, **kwargs):
        user = request.env.user
        event = request.env['absar.sales.bell.event'].sudo().browse(event_id).exists()
        if not event or event.user_id.id != user.id or event.company_id not in user.company_ids:
            raise NotFound()
        event.write({'is_read': True})
        return request.redirect('/my/employee/sales/%s' % event.order_id.id)
