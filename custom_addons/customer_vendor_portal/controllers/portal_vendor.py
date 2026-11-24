# -*- coding: utf-8 -*-
from odoo import http
from werkzeug.exceptions import NotFound
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.addons.web.controllers.home import Home


class VendorPortalLogin(Home):

    def _login_redirect(self, uid, redirect=None):
        """Hook called by Odoo 18 after successful login to determine redirect target."""
        if redirect:
            return redirect
        user = request.env['res.users'].sudo().browse(uid)
        partner = user.partner_id
        if user._is_portal() and partner.supplier_rank:
            if not partner.vendor_portal_onboarded:
                return '/my/account'
            return '/vendor/dashboard'
        return super()._login_redirect(uid, redirect=redirect)


class VendorPortal(CustomerPortal):

    # ---------------------------------------------------------
    # VENDOR ENTRY POINT
    # ---------------------------------------------------------
    @http.route(['/vendor'], type='http', auth='user', website=True)
    def vendor_home(self, **kw):
        if not request.env.user._is_portal() or not request.env.user.partner_id.supplier_rank:
            return request.redirect('/my/home')
        return request.redirect('/vendor/dashboard')

    # ---------------------------------------------------------
    # OVERRIDE /my/home — catch any stray redirects
    # ---------------------------------------------------------
    @http.route(['/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        partner = request.env.user.partner_id
        if request.env.user._is_portal() and partner.supplier_rank:
            return request.redirect('/vendor/dashboard')
        return super().home(**kw)

    # ---------------------------------------------------------
    # OVERRIDE /my and /my/account
    # ---------------------------------------------------------
    @http.route(['/my', '/my/account'], type='http', auth='user', website=True)
    def account(self, redirect=None, **post):
        partner = request.env.user.partner_id

        if request.env.user._is_portal() and partner.supplier_rank:
            if post:
                super().account(redirect=None, **post)
                if not partner.vendor_portal_onboarded:
                    partner.sudo().write({'vendor_portal_onboarded': True})
                return request.redirect('/vendor/dashboard')

            if not partner.vendor_portal_onboarded:
                return super().account(redirect=redirect, **post)

            return request.redirect('/vendor/dashboard')

        return super().account(redirect=redirect, **post)

    # ---------------------------------------------------------
    def _vendor_partner(self):
        partner = request.env.user.partner_id
        if not request.env.user._is_portal() or not partner.supplier_rank:
            raise NotFound()
        return partner

    def _vendor_po_domain(self, partner):
        return [
            ('partner_id', '=', partner.id),
            ('state', 'in', ['purchase', 'done']),
            ('company_id', 'in', request.env.user.company_ids.ids),
        ]

    # VENDOR DASHBOARD
    # ---------------------------------------------------------
    @http.route(['/vendor/dashboard'], type='http', auth='user', website=True)
    def vendor_dashboard(self, **kw):
        partner = self._vendor_partner()

        Invoice = request.env['portal.vendor.invoice'].sudo()
        domain = [('partner_id', '=', partner.id)]
        all_invoices = Invoice.search(domain)

        po_count = request.env['purchase.order'].sudo().search_count(self._vendor_po_domain(partner))

        stats = {
            'total': len(all_invoices),
            'po_count': po_count,
            'submitted': len(all_invoices.filtered(lambda i: i.state == 'submitted')),
            'review': len(all_invoices.filtered(lambda i: i.state == 'review')),
            'approved': len(all_invoices.filtered(lambda i: i.state == 'approved')),
            'rejected': len(all_invoices.filtered(lambda i: i.state == 'rejected')),
            'total_amount': sum(all_invoices.filtered(lambda i: i.state == 'approved').mapped('amount_total')),
            'currency': request.env.company.currency_id,
        }

        recent_invoices = Invoice.search(domain, limit=5, order='create_date desc')

        return request.render('customer_vendor_portal.vendor_dashboard', {
            'partner': partner,
            'stats': stats,
            'recent_invoices': recent_invoices,
            'page_name': 'vendor_dashboard',
        })

    # ---------------------------------------------------------
    # PURCHASE ORDER LIST
    # ---------------------------------------------------------
    @http.route(['/vendor/pos'], type='http', auth='user', website=True)
    def vendor_po_list(self, page=1, **kw):
        partner = self._vendor_partner()

        PO = request.env['purchase.order'].sudo()
        domain = self._vendor_po_domain(partner)
        pos_count = PO.search_count(domain)
        pager = portal_pager(url='/vendor/pos', total=pos_count, page=page, step=10)
        pos = PO.search(domain, limit=10, offset=pager['offset'], order='date_approve desc')

        return request.render('customer_vendor_portal.vendor_po_list', {
            'pos': pos, 'pager': pager, 'page_name': 'vendor_pos',
        })

    # ---------------------------------------------------------
    # PURCHASE ORDER DETAIL
    # ---------------------------------------------------------
    @http.route(['/vendor/po/<int:po_id>'], type='http', auth='user', website=True)
    def vendor_po_detail(self, po_id, **kw):
        partner = self._vendor_partner()
        po = request.env['purchase.order'].sudo().search(
            self._vendor_po_domain(partner) + [('id', '=', po_id)], limit=1,
        )
        if not po:
            return request.redirect('/vendor/pos')
        return request.render('customer_vendor_portal.vendor_po_detail', {
            'po': po, 'page_name': 'vendor_pos',
        })

    # ---------------------------------------------------------
    # VENDOR INVOICE LIST
    # ---------------------------------------------------------
    @http.route(['/vendor/invoices'], type='http', auth='user', website=True)
    def vendor_invoice_list(self, page=1, state=None, **kw):
        partner = self._vendor_partner()

        Invoice = request.env['portal.vendor.invoice'].sudo()
        domain = [('partner_id', '=', partner.id)]
        if state and state in ('submitted', 'review', 'approved', 'rejected'):
            domain.append(('state', '=', state))

        invoice_count = Invoice.search_count(domain)
        pager = portal_pager(
            url='/vendor/invoices',
            url_args={'state': state or ''},
            total=invoice_count,
            page=page,
            step=15,
        )
        invoices = Invoice.search(domain, limit=15, offset=pager['offset'])

        return request.render('customer_vendor_portal.vendor_invoice_list', {
            'invoices': invoices,
            'pager': pager,
            'active_state': state or '',
            'page_name': 'vendor_invoices',
        })

    # ---------------------------------------------------------
    # VENDOR INVOICE DETAIL
    # ---------------------------------------------------------
    @http.route(['/vendor/invoice/<int:invoice_id>'], type='http', auth='user', website=True)
    def vendor_invoice_detail(self, invoice_id, **kw):
        partner = self._vendor_partner()
        inv = request.env['portal.vendor.invoice'].sudo().browse(invoice_id)
        if not inv.exists() or inv.partner_id.id != partner.id:
            return request.redirect('/vendor/invoices')
        return request.render('customer_vendor_portal.vendor_invoice_detail', {
            'invoice': inv,
            'page_name': 'vendor_invoices',
        })

    @http.route(['/vendor/invoice/upload'], type='http', auth='user', methods=['GET'], website=True)
    def vendor_invoice_upload_form(self, **kw):
        self._vendor_partner()
        return request.redirect('/vendor/invoices')
