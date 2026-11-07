# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError


class EmployeePortalPurchaseOrder(http.Controller):
    """Secure bridge from portal records to an already signed Purchase Order."""

    def _is_ceo(self, user):
        return user.has_group('employee_portal_suite.group_employee_portal_ceo')

    def _find_po_sign_request(self, purchase_order):
        SignRequest = request.env['sign.request'].sudo()

        # Prefer an explicit relation when another custom module adds one.
        relation_fields = (
            'purchase_order_id',
            'purchase_id',
            'po_id',
        )
        for field_name in relation_fields:
            if field_name in SignRequest._fields:
                sign_request = SignRequest.search([
                    (field_name, '=', purchase_order.id),
                ], order='create_date desc', limit=1)
                if sign_request:
                    return sign_request

        # Standard/custom source-document references, when available.
        source_candidates = (
            ('reference', purchase_order.name),
            ('reference', purchase_order.display_name),
            ('name', purchase_order.name),
            ('subject', purchase_order.name),
            ('message', purchase_order.name),
        )
        for field_name, value in source_candidates:
            if field_name in SignRequest._fields and value:
                sign_request = SignRequest.search([
                    (field_name, 'ilike', value),
                ], order='create_date desc', limit=1)
                if sign_request:
                    return sign_request

        return SignRequest.browse()

    @http.route(
        '/my/employee/purchase-order/<int:purchase_order_id>/signed',
        type='http',
        auth='user',
        website=True,
        sitemap=False,
    )
    def portal_view_signed_purchase_order(self, purchase_order_id, **kwargs):
        user = request.env.user
        if not self._is_ceo(user):
            raise AccessError('Only the CEO portal group can open signed purchase orders from payment approvals.')

        purchase_order = request.env['purchase.order'].sudo().browse(purchase_order_id).exists()
        if (
            not purchase_order
            or purchase_order.company_id not in user.company_ids
        ):
            return request.not_found()

        sign_request = self._find_po_sign_request(purchase_order)
        if not sign_request:
            return request.render(
                'employee_portal_suite.portal_signed_po_not_found',
                {'purchase_order': purchase_order},
            )

        # A completed request should be opened as its final signed PDF. This is
        # read-only and does not expose signing/modification actions.
        if sign_request.state == 'signed' and sign_request.access_token:
            return request.redirect(
                '/sign/download/%s/%s/completed' % (
                    sign_request.id,
                    sign_request.access_token,
                )
            )

        # If the CEO is one of the signers, reuse Odoo Sign's existing portal page.
        sign_item = sign_request.request_item_ids.filtered(
            lambda item: item.partner_id == user.partner_id
        )[:1]
        if sign_item and sign_item.access_token:
            return request.redirect(
                '/sign/document/%s/%s?portal=1' % (
                    sign_request.id,
                    sign_item.access_token,
                )
            )

        return request.render(
            'employee_portal_suite.portal_signed_po_not_ready',
            {
                'purchase_order': purchase_order,
                'sign_request': sign_request,
            },
        )
