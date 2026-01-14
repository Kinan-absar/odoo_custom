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
        partner = request.env.user.partner_id

        # Load your Module 1 statement lines
        Statement = request.env['customer.statement.line']
        domain = [('partner_id', '=', partner.id)]
        lines = Statement.sudo().search(domain, order='date asc')

        values = {
            'statement_lines': lines,
            'page_name': 'customer_statements',
        }
        return request.render('customer_vendor_portal.customer_statement_page', values)

    # ---------------------------------------------------------
    # CUSTOMER INVOICE LIST
    # ---------------------------------------------------------
    @http.route(['/my/customer_invoices'], type='http', auth='user', website=True)
    def portal_my_customer_invoices(self, page=1, **kwargs):
        partner = request.env.user.partner_id

        Invoice = request.env['account.move']
        domain = [
            ('move_type', '=', 'out_invoice'),
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
        domain = [('partner_id', '=', partner.id)]

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
