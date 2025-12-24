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

        # correct signing order → mail_sent_order
        items_sorted = items.sorted(lambda x: x.mail_sent_order or 0)

        # find the next signer
        next_item = next((it for it in items_sorted if it.state not in ("completed", "canceled")), None)

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
    def portal_employee_sign_docs(self, filter="pending", **kwargs):
        user = request.env.user
        partner = user.partner_id
        SignItem = request.env["sign.request.item"].sudo()

        # retrieve only items that belong to this user
        my_items = SignItem.search([("partner_id", "=", partner.id)])

        documents = []

        for item in my_items:
            req = item.sign_request_id

            # sorted order by mail_sent_order
            items_sorted = req.request_item_ids.sorted(lambda x: x.mail_sent_order or 0)

            # first signer that must act (pending)
            first_pending = next((
                it for it in items_sorted
                if it.state not in ("completed", "canceled")
            ), None)

            # FILTER LOGIC
            if filter == "pending":
                # user ONLY sees docs when it's their turn
                if not first_pending or first_pending.id != item.id:
                    continue

            if filter == "signed" and item.state != "completed":
                continue

            if filter == "rejected" and item.state != "canceled":
                continue

            # build document row
            documents.append({
                "item": item,
                "filename": req.reference,
                "date": req.create_date.date(),
                "your_status": self._compute_personal_status(item),
                "workflow_status": self._compute_workflow_status(req),
                "sign_url": item._get_share_url(),  # Odoo official signer URL
                "access_token": item.access_token,   # NECESSARY for summary
            })
        # Sort newest → oldest
        documents = sorted(documents, key=lambda d: d["date"], reverse=True)

        return request.render("employee_portal_suite.portal_sign_documents_page", {
            "documents": documents,
            "current_filter": filter,
        })
