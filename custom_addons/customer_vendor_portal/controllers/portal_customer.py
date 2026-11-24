# -*- coding: utf-8 -*-
from odoo import http, _, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class CustomerPortalExtended(CustomerPortal):

    # ---------------------------------------------------------
    # CUSTOMER STATEMENT PAGE
    # ---------------------------------------------------------
    @http.route(['/my/statements'], type='http', auth='user', website=True)
    def portal_my_statements(self, **kwargs):
        # Accounting statement workspaces can include drafts, opening balances
        # and other internal adjustments. The portal presents posted invoices.
        return request.redirect('/my/customer_invoices')

    # ---------------------------------------------------------
    # CUSTOMER INVOICE LIST
    # ---------------------------------------------------------
    @http.route(['/my/customer_invoices'], type='http', auth='user', website=True)
    def portal_my_customer_invoices(self, page=1, **kwargs):
        partner = request.env.user.partner_id

        Invoice = request.env['account.move']
        domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('company_id', 'in', request.env.user.company_ids.ids),
            ('partner_id', '=', partner.id),
        ]

        invoice_count = Invoice.sudo().search_count(domain)
        pager = portal_pager(
            url='/my/customer_invoices',
            total=invoice_count,
            page=page,
            step=10
        )

        invoices = Invoice.sudo().search(domain, limit=10, offset=pager['offset'])

        values = {
            'invoices': invoices,
            'pager': pager,
            'page_name': 'customer_invoices',
        }
        return request.render('customer_vendor_portal.customer_invoice_list', values)

    # ---------------------------------------------------------
    # CUSTOMER SALES ORDERS
    # ---------------------------------------------------------
    @http.route(['/my/sales_orders'], type='http', auth='user', website=True)
    def portal_my_sales_orders(self, page=1, **kwargs):
        partner = request.env.user.partner_id

        SaleOrder = request.env['sale.order']
        domain = [
            ('partner_id', '=', partner.id),
            ('state', 'in', ['sent', 'sale', 'done']),
            ('company_id', 'in', request.env.user.company_ids.ids),
        ]

        sales_count = SaleOrder.sudo().search_count(domain)
        pager = portal_pager(
            url='/my/sales_orders',
            total=sales_count,
            page=page,
            step=10
        )

        sales_orders = SaleOrder.sudo().search(domain, limit=10, offset=pager['offset'])

        values = {
            'sales_orders': sales_orders,
            'pager': pager,
            'page_name': 'customer_sales_orders',
        }
        return request.render('customer_vendor_portal.customer_sales_list', values)
