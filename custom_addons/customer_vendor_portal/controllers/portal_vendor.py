# -*- coding: utf-8 -*-
import base64
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class VendorPortal(CustomerPortal):

    # ---------------------------------------------------------------
    # VENDOR ENTRY POINT — smart first-login redirect
    # ---------------------------------------------------------------
    @http.route(['/vendor'], type='http', auth='user', website=True)
    def vendor_home(self, **kw):
        user = request.env.user
        partner = user.partner_id
        if not partner.supplier_rank:
            return request.redirect('/my/home')
        return request.redirect('/my/home')

    # ---------------------------------------------------------------
    # OVERRIDE /my and /my/account — first-login onboarding logic
    # ---------------------------------------------------------------
    @http.route(['/my', '/my/account'], type='http', auth='user', website=True)
    def account(self, redirect=None, **post):
        user = request.env.user
        partner = user.partner_id

        # POST: vendor saved their details → mark onboarding done, go to dashboard
        if post and partner.supplier_rank:
            result = super().account(redirect=None, **post)
            partner.sudo().write({'vendor_portal_onboarded': True})
            return request.redirect('/my/home')

        # GET for vendor:
        if partner.supplier_rank:
            if partner.vendor_portal_onboarded:
                # Already onboarded → skip details page, go to dashboard
                return request.redirect('/my/home')
            else:
                # First login → show account details so they can complete profile
                return super().account(redirect=redirect, **post)

        # Non-vendor: normal behaviour
        return super().account(redirect=redirect, **post)

    # ---------------------------------------------------------------
    # VENDOR DASHBOARD (home)
    # ---------------------------------------------------------------
    @http.route(['/my/home'], type='http', auth='user', website=True)
    def vendor_dashboard(self, **kw):
        user = request.env.user
        partner = user.partner_id

        if not partner.supplier_rank:
            return super().home(**kw) if hasattr(super(), 'home') else request.render('portal.portal_my_home', {})

        Invoice = request.env['portal.vendor.invoice'].sudo()
        domain = [('partner_id', '=', partner.id)]
        all_invoices = Invoice.search(domain)

        stats = {
            'total': len(all_invoices),
            'submitted': len(all_invoices.filtered(lambda i: i.state == 'submitted')),
            'review': len(all_invoices.filtered(lambda i: i.state == 'review')),
            'approved': len(all_invoices.filtered(lambda i: i.state == 'approved')),
            'rejected': len(all_invoices.filtered(lambda i: i.state == 'rejected')),
            'total_amount': sum(all_invoices.filtered(lambda i: i.state == 'approved').mapped('amount_total')),
            'currency': request.env.company.currency_id,
        }

        recent_invoices = Invoice.search(domain, limit=5, order='create_date desc')
        po_count = request.env['purchase.order'].sudo().search_count([
            ('partner_id', '=', partner.id),
            ('state', 'in', ['purchase', 'done']),
        ])

        values = {
            'partner': partner,
            'stats': stats,
            'recent_invoices': recent_invoices,
            'po_count': po_count,
            'page_name': 'vendor_dashboard',
        }
        return request.render('customer_vendor_portal.vendor_dashboard', values)

    # ---------------------------------------------------------------
    # PURCHASE ORDER LIST
    # ---------------------------------------------------------------
    @http.route(['/vendor/pos'], type='http', auth='user', website=True)
    def vendor_po_list(self, page=1, **kw):
        partner = request.env.user.partner_id
        if not partner.supplier_rank:
            return request.redirect('/my/home')

        PO = request.env['purchase.order']
        domain = [('partner_id', '=', partner.id), ('state', 'in', ['purchase', 'done'])]
        pos_count = PO.search_count(domain)
        pager = portal_pager(url='/vendor/pos', total=pos_count, page=page, step=10)
        pos = PO.search(domain, limit=10, offset=pager['offset'], order='date_approve desc')

        return request.render('customer_vendor_portal.vendor_po_list', {
            'pos': pos, 'pager': pager, 'page_name': 'vendor_pos',
        })

    # ---------------------------------------------------------------
    # PURCHASE ORDER DETAIL
    # ---------------------------------------------------------------
    @http.route(['/vendor/po/<int:po_id>'], type='http', auth='user', website=True)
    def vendor_po_detail(self, po_id, **kw):
        partner = request.env.user.partner_id
        po = request.env['purchase.order'].sudo().browse(po_id)
        if not po.exists() or po.partner_id.id != partner.id or po.state not in ['purchase', 'done']:
            return request.redirect('/vendor/pos')
        return request.render('customer_vendor_portal.vendor_po_detail', {'po': po, 'page_name': 'vendor_pos'})

    # ---------------------------------------------------------------
    # VENDOR INVOICE LIST
    # ---------------------------------------------------------------
    @http.route(['/vendor/invoices'], type='http', auth='user', website=True)
    def vendor_invoice_list(self, page=1, state=None, **kw):
        partner = request.env.user.partner_id
        if not partner.supplier_rank:
            return request.redirect('/my/home')

        Invoice = request.env['portal.vendor.invoice']
        domain = [('partner_id', '=', partner.id)]
        if state and state in ('submitted', 'review', 'approved', 'rejected'):
            domain.append(('state', '=', state))

        invoice_count = Invoice.search_count(domain)
        pager = portal_pager(url='/vendor/invoices', url_args={'state': state or ''}, total=invoice_count, page=page, step=15)
        invoices = Invoice.search(domain, limit=15, offset=pager['offset'])

        submitted = request.httprequest.args.get('submitted')

        return request.render('customer_vendor_portal.vendor_invoice_list', {
            'invoices': invoices,
            'pager': pager,
            'active_state': state or '',
            'submitted': submitted,
            'page_name': 'vendor_invoices',
        })

    # ---------------------------------------------------------------
    # VENDOR INVOICE DETAIL
    # ---------------------------------------------------------------
    @http.route(['/vendor/invoice/<int:invoice_id>'], type='http', auth='user', website=True)
    def vendor_invoice_detail(self, invoice_id, **kw):
        partner = request.env.user.partner_id
        inv = request.env['portal.vendor.invoice'].sudo().browse(invoice_id)
        if not inv.exists() or inv.partner_id.id != partner.id:
            return request.redirect('/vendor/invoices')
        return request.render('customer_vendor_portal.vendor_invoice_detail', {
            'invoice': inv,
            'page_name': 'vendor_invoices',
        })

    # ---------------------------------------------------------------
    # UPLOAD VENDOR INVOICE (GET)
    # ---------------------------------------------------------------
    @http.route(['/vendor/invoice/upload'], type='http', auth='user', methods=['GET'], website=True)
    def vendor_invoice_upload_form(self, **kw):
        partner = request.env.user.partner_id
        if not partner.supplier_rank:
            return request.redirect('/my/home')

        purchase_orders = request.env['purchase.order'].sudo().search([
            ('partner_id', '=', partner.id),
            ('state', 'in', ['purchase', 'done']),
        ])
        return request.render('customer_vendor_portal.vendor_invoice_upload_form', {
            'purchase_orders': purchase_orders,
            'page_name': 'vendor_upload',
        })

    # ---------------------------------------------------------------
    # SUBMIT INVOICE (POST)
    # ---------------------------------------------------------------
    @http.route(['/vendor/invoice/upload'], type='http', auth='user',
                methods=['POST'], website=True, csrf=True)
    def vendor_invoice_upload(self, **post):
        user = request.env.user
        partner = user.partner_id

        if not partner.supplier_rank:
            return request.redirect('/my/home')

        po_id = int(post.get('po_id') or 0)
        file = post.get('invoice_file')
        attachment_id = False

        if file and hasattr(file, 'filename') and file.filename:
            file_data = file.read()
            if file_data:
                attachment_id = request.env['ir.attachment'].sudo().create({
                    'name': file.filename,
                    'datas': base64.b64encode(file_data).decode(),
                    'type': 'binary',
                    'res_model': 'portal.vendor.invoice',
                    'res_id': 0,
                }).id

        try:
            request.env['portal.vendor.invoice'].sudo().create({
                'partner_id': partner.id,
                'po_id': po_id or False,
                'amount_total': float(post.get('amount_total') or 0),
                'invoice_date': post.get('invoice_date') or False,
                'notes': post.get('notes') or False,
                'attachment_id': attachment_id or False,
                'portal_user_id': user.id,
                'vendor_invoice_number': post.get('vendor_invoice_number') or False,
            })
        except Exception:
            request.env.cr.rollback()
            purchase_orders = request.env['purchase.order'].sudo().search([
                ('partner_id', '=', partner.id),
                ('state', 'in', ['purchase', 'done']),
            ])
            return request.render('customer_vendor_portal.vendor_invoice_upload_form', {
                'purchase_orders': purchase_orders,
                'error_message': _('This invoice number already exists for your account. Please use a unique invoice number.'),
                'form_data': post,
                'page_name': 'vendor_upload',
            })

        return request.redirect('/vendor/invoices?submitted=1')
