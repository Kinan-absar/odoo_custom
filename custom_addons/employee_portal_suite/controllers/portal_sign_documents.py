# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class EmployeePortalSignDocs(CustomerPortal):

    # -------------------------------
    # Personal status
    # -------------------------------
    def _compute_personal_status(self, item):
        state = item.state

        if state in ("draft", "sent"):
            return "🟡 Pending"
        if state == "completed":
            return "🟢 Signed"
        if state == "canceled":
            return "🔴 Rejected"

        return "⚪ Unknown"

    # -------------------------------
    # Workflow: respecting signing order
    # -------------------------------
    def _compute_workflow_status(self, sign_request):
        items = sign_request.request_item_ids

        # fully signed
        if all(it.state == "completed" for it in items):
            return "🟢 Fully Signed"

        # rejected
        canceled = next((it for it in items if it.state == "canceled"), None)
        if canceled:
            return f"🔴 Rejected by {canceled.partner_id.name}"

        # Prefer Odoo Sign's actual active signer.  With Signing Order enabled
        # the active request item is ``sent`` while later signers stay ``draft``.
        # Keep an ordered incomplete fallback for legacy/non-sequential requests.
        active_items = items.filtered(lambda it: it.state == "sent")
        next_item = active_items.sorted(lambda x: (x.mail_sent_order or 0, x.id))[:1]
        if not next_item:
            items_sorted = items.sorted(lambda x: (x.mail_sent_order or 0, x.id))
            next_item = next((
                it for it in items_sorted
                if it.state not in ("completed", "canceled")
            ), None)
        elif hasattr(next_item, 'ensure_one'):
            next_item = next_item[:1]

        if next_item:
            current_user_partner = request.env.user.partner_id

            if next_item.partner_id.id == current_user_partner.id:
                return "🖊️ To Sign"
            else:
                return f"⏳ Waiting: {next_item.partner_id.name}"

        return "⚪ Unknown"

    # -------------------------------
    # Main route
    # -------------------------------
    @http.route('/my/employee/sign', type='http', auth='user', website=True)
    def portal_employee_sign_docs(self, filter="pending", search=None, **kwargs):

        user = request.env.user
        if not user.share:
            return request.redirect('/web')
        partner = user.partner_id
        SignItem = request.env["sign.request.item"].sudo()

        my_items = SignItem.search([("partner_id", "=", partner.id)])

        documents = []

        for item in my_items:
            req = item.sign_request_id

            # -------------------------
            # SEARCH FILTER (by reference)
            # -------------------------
            if search:
                if not req.reference or search.lower() not in req.reference.lower():
                    continue

            # -------------------------
            # FILTER LOGIC
            # -------------------------
            # Odoo Sign owns the signing-order state machine.  For sequential
            # requests the currently active signer is the request item whose
            # state is ``sent``; future signers normally remain ``draft`` until
            # their turn.  Trust that state instead of trying to reconstruct the
            # sequence in the portal, otherwise a valid portal signer can vanish
            # from Pending when Odoo changes how mail_sent_order is populated.
            if filter == "pending":
                if item.state != "sent":
                    continue

            elif filter == "signed":
                if item.state != "completed":
                    continue

            elif filter == "rejected":
                if item.state != "canceled":
                    continue

            # -------------------------
            # BUILD DOCUMENT ENTRY
            # -------------------------
            documents.append({
                "item": item,
                "filename": req.reference,
                "date": req.create_date.date(),
                "your_status": self._compute_personal_status(item),
                "workflow_status": self._compute_workflow_status(req),
                # Use the canonical Odoo Sign document route explicitly.
                # _get_share_url() can resolve to portal/list routes depending on
                # context, which made the Employee Portal Sign button appear to
                # do nothing for some request items.
                "sign_url": (
                    "/sign/document/%s/%s?portal=1"
                    % (req.id, item.access_token)
                    if item.access_token else False
                ),
                "access_token": item.access_token,
            })

        # Sort newest → oldest
        documents = sorted(documents, key=lambda d: d["date"], reverse=True)

        # Clear the "new signature request" badge on the dashboard/header bell
        # now that the user has opened this page.
        request.env['portal.report.seen'].sudo()._mark_seen(user.id, 'sign_request')

        return request.render(
            "employee_portal_suite.portal_sign_documents_page",
            {
                "documents": documents,
                "current_filter": filter,
                "search": search or "",
            }
        )

