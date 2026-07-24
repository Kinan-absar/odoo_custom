from odoo import http, fields, _
from odoo.http import request
import base64

def _mr_status_badge(rec):
    state = rec.state

    # FULLY APPROVED
    if state == "approved":
        return '<span class="badge bg-success">Fully Approved</span>'

    # REJECTED
    if state == "rejected":
        stage_labels = {
            'purchase': 'Purchase Rep',
            'store': 'Store Manager',
            'project_manager': 'Project Manager',
            'director': 'Director',
            'ceo': 'CEO',
        }
        lbl = stage_labels.get(rec.state_before_reject, "Unknown Stage")

        reasons = {
            'purchase': rec.purchase_comment,
            'store': rec.store_comment,
            'project_manager': rec.project_manager_comment,
            'director': rec.director_comment,
            'ceo': rec.ceo_comment,
        }
        reason = reasons.get(rec.state_before_reject) or "No reason"

        return f'<span class="badge bg-danger">Rejected — {lbl} Stage ({reason})</span>'
        # CLARIFICATION OVERRIDE
    if rec.needs_clarification and rec.clarification_stage:
        stage_labels = {
            'purchase': 'Purchase Rep',
            'store': 'Store Manager',
            'project_manager': 'Project Manager',
            'director': 'Director',
            'ceo': 'CEO',
        }
        clar_label = stage_labels.get(rec.clarification_stage, rec.clarification_stage)
        return f'<span class="badge bg-info text-dark">🚩 Clarification — {clar_label}</span>'

    # PENDING STAGE BADGES
    stage_badges = {
        'purchase': 'Pending Purchase Rep',
        'store': 'Pending Store Manager',
        'project_manager': 'Pending Project Manager',
        'director': 'Pending Director',
        'ceo': 'Pending CEO',
    }

    if state in stage_badges:
        return f'<span class="badge bg-warning text-dark">{stage_badges[state]}</span>'

    return '<span class="badge bg-secondary">Unknown</span>'

class EmployeePortalMaterialRequests(http.Controller):

    # ---------------------------------------------------------
    # Helper
    # ---------------------------------------------------------
    def _employee(self):
        return request.env.user.employee_id

    # ---------------------------------------------------------
    # LIST OWN MATERIAL REQUESTS  (Employee View)
    # ---------------------------------------------------------
    @http.route("/my/employee/material", type="http", auth="user", website=True)
    def list_material(self, **kw):
        emp = self._employee()
        if not emp:
            return request.redirect("/my")

        search = kw.get("search")

        domain = [("employee_id", "=", emp.id)]

        # If user typed something in search bar, search by MR number, employee, worksite, item name, or linked PO.
        if search:
            domain += ["|", "|", "|", "|",
                ("name", "ilike", search),
                ("employee_id.name", "ilike", search),
                ("worksite", "ilike", search),
                ("line_ids.item_name", "ilike", search),
                ("purchase_order_ids.name", "ilike", search),
            ]

        records = request.env["material.request"].sudo().search(domain, order="id desc")

        return request.render(
            "employee_portal_suite.employee_material_requests_page",
            {
                "requests": records,
                "status_badge": _mr_status_badge,
                "search": search,   # VERY IMPORTANT
            },
        )



    # ---------------------------------------------------------
    # DETAIL PAGE
    # ---------------------------------------------------------
    @http.route("/my/employee/material/<int:req_id>", type="http", auth="user", website=True)
    def material_detail(self, req_id, **kw):
        emp = self._employee()
        rec = request.env["material.request"].sudo().browse(req_id)

        if not rec.exists() or rec.employee_id != emp:
            return request.redirect("/my")

        attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "material.request"),
            ("res_id", "=", rec.id)
        ])

        return request.render("employee_portal_suite.employee_material_request_detail_page", {
            "request_rec": rec,
            "attachments": attachments,     # ← ADDED
            "status_badge": _mr_status_badge,
        })


    # ---------------------------------------------------------
    # NEW FORM
    # ---------------------------------------------------------
    @http.route("/my/employee/material/new", type="http", auth="user", website=True)
    def material_new(self, **kw):
        emp = self._employee()
        if not emp:
            return request.redirect("/my")

        uoms = request.env["uom.uom"].sudo().search([])
        projects = emp.sudo()._get_material_request_projects()

        return request.render("employee_portal_suite.employee_material_request_new_form", {
            "uoms": uoms,
            "projects": projects,
            "single_project": projects[:1] if len(projects) == 1 else False,
        })

    # ---------------------------------------------------------
    # CREATE REQUEST
    # ---------------------------------------------------------
    @http.route("/my/employee/material/create", type="http", auth="user", website=True, csrf=True)
    def material_create(self, **post):
        emp = self._employee()
        if not emp:
            return request.redirect("/my")

        projects = emp.sudo()._get_material_request_projects()
        project_id = int(post.get("project_id") or 0)
        selected_project = request.env["project.project"].sudo().browse(project_id)
        if not selected_project.exists() or selected_project not in projects:
            return request.render("employee_portal_suite.employee_material_request_new_form", {
                "uoms": request.env["uom.uom"].sudo().search([]),
                "projects": projects,
                "single_project": projects[:1] if len(projects) == 1 else False,
                "error_message": _("Please select one of the projects configured on your work location."),
            })

        # Create main request
        rec = request.env["material.request"].sudo().create({
            "employee_id": emp.id,
            "project_id": selected_project.id,
            "worksite": post.get("worksite"),
            "delivery_date": post.get("delivery_date"),
        })

        # Lines
        i = 0
        while True:
            name = post.get(f"item_name_{i}")
            if name is None:
                break

            if name.strip():
                qty = post.get(f"qty_required_{i}")
                uom = post.get(f"uom_id_{i}")

                request.env["material.request.line"].sudo().create({
                    "request_id": rec.id,
                    "item_name": name,
                    "qty_required": qty or 0,
                    "uom_id": int(uom) if uom else False,
                })

            i += 1



        rec.sudo().action_submit()
        # --- SAVE ATTACHMENTS FROM NEW FORM ---
        files = request.httprequest.files.getlist("attachments")
        tag = post.get("attachment_tag") or "General"

        for f in files:
            if not f or f.filename.strip() == "":
                continue
            filename = f.filename.strip()
            file_content = f.read()

            request.env["ir.attachment"].sudo().create({
                "name": filename,
                "datas": base64.b64encode(file_content).decode(),
                "mimetype": f.mimetype,
                "res_model": "material.request",
                "res_id": rec.id,
                "type": "binary",
                "description": tag,
                "public": True,   # ← THIS IS THE MAGIC FIX
            })

        return request.redirect(f"/my/employee/material/{rec.id}")

    # ---------------------------------------------------------
    # MATERIAL REQUEST — APPROVAL LIST (PENDING / APPROVED / REJECTED / ALL)
    # ---------------------------------------------------------
    @http.route("/my/employee/material/approvals", type="http", auth="user", website=True)
    def material_approvals(self, **kw):
        user = request.env.user
        Material = request.env["material.request"].sudo()

        # Only approvers allowed
        if not (
            user.has_group("employee_portal_suite.group_employee_portal_ceo")
            or user.has_group("employee_portal_suite.group_mr_purchase_rep")
            or user.has_group("employee_portal_suite.group_mr_store_manager")
            or user.has_group("employee_portal_suite.group_mr_project_manager")
            or user.has_group("employee_portal_suite.group_mr_projects_director")
        ):
            return request.redirect('/my')

        current_filter = kw.get("filter", "all")
        search = (kw.get("search") or "").strip()

        # ---------------------------------------------------------
        # 1) PENDING LIST — currently waiting for THIS user
        # ---------------------------------------------------------
        pending_list = []

        for rec in Material.search([
            ("state", "in", ["purchase", "store", "project_manager", "director", "ceo"])
        ]):

            # -------------------------------
            # STORE MANAGER (project-based)
            # -------------------------------
            if rec.state == "store":
                if user == rec.store_manager_user_id:
                    pending_list.append(rec)

            # -------------------------------
            # PROJECT MANAGER (project-based)
            # -------------------------------
            elif rec.state == "project_manager":
                if user == rec.project_manager_user_id:
                    pending_list.append(rec)

            # -------------------------------
            # GLOBAL STAGES (group-based)
            # -------------------------------
            elif rec.state == "purchase" and user.has_group(
                "employee_portal_suite.group_mr_purchase_rep"
            ):
                pending_list.append(rec)

            elif rec.state == "director" and user.has_group(
                "employee_portal_suite.group_mr_projects_director"
            ):
                pending_list.append(rec)

            elif rec.state == "ceo" and user.has_group(
                "employee_portal_suite.group_employee_portal_ceo"
            ):
                pending_list.append(rec)

        # ---------------------------------------------------------
        # 2) APPROVED LIST
        # Show only requests already approved by THIS user, even if the MR
        # is now waiting at a later approval stage. Do not show every fully
        # approved MR to Purchase Rep unless they personally approved it.
        # ---------------------------------------------------------
        approved_domain = [
            "|", "|", "|", "|",
            ("purchase_approved_by", "=", user.id),
            ("store_approved_by", "=", user.id),
            ("project_manager_approved_by", "=", user.id),
            ("director_approved_by", "=", user.id),
            ("ceo_approved_by", "=", user.id),
        ]
        approved_list = Material.search(approved_domain, order="id desc")

        # ---------------------------------------------------------
        # 3) REJECTED LIST — ONLY if user rejected
        # ---------------------------------------------------------
        rejected_list = Material.search([
            ("state", "=", "rejected"),
            ("rejected_by", "=", user.id),
        ])

        # ---------------------------------------------------------
        # 4) ALL LIST — union
        # ---------------------------------------------------------
        all_reqs = list({*pending_list, *approved_list, *rejected_list})

        # ---------------------------------------------------------
        # 5) Choose what to show
        # ---------------------------------------------------------
        shown_reqs = {
            "pending": pending_list,
            "approved": approved_list,
            "rejected": rejected_list,
            "all": all_reqs,
        }.get(current_filter, pending_list)
        # -----------------------------
        # SEARCH FILTER
        # Search by MR number, employee, worksite, item/material name, or linked PO.
        # -----------------------------
        if search:
            term = search.lower()

            def _matches_search(r):
                values = [
                    r.name or "",
                    r.employee_id.name or "",
                    r.worksite or "",
                    r.po_name or "",
                ]
                values += [line.item_name or "" for line in r.line_ids]
                return any(term in value.lower() for value in values)

            shown_reqs = [r for r in shown_reqs if _matches_search(r)]

        # Clear the "new approval" badge on the dashboard/header bell now that
        # the user has opened the material approvals list.
        request.env['portal.report.seen'].sudo()._mark_seen(user.id, 'mr_approval')

        return request.render("employee_portal_suite.portal_material_approvals_list", {
            "pending_reqs": pending_list,
            "approved_reqs": approved_list,
            "rejected_reqs": rejected_list,
            "all_reqs": all_reqs,
            "shown_reqs": shown_reqs,
            "current_filter": current_filter,
            "search": search,  # <-- ADD THIS
            "status_badge": _mr_status_badge,  # <= pass badge renderer
        })



    # ---------------------------------------------------------
    # APPROVAL DETAIL PAGE
    # ---------------------------------------------------------
    @http.route("/my/employee/material/approvals/<int:req_id>", type="http", auth="user", website=True)
    def material_approval_detail(self, req_id, **kw):
        rec = request.env["material.request"].sudo().browse(req_id)

        if not rec.exists():
            return request.redirect("/my")

        all_attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "material.request"),
            ("res_id", "=", rec.id)
        ])
        accounting_attachments = all_attachments.filtered(
            lambda att: (att.description or "") == "Accounting Documents"
        )
        quotation_attachments = all_attachments.filtered(
            lambda att: (att.description or "") == "Quotation Documents"
        )
        attachments = all_attachments - accounting_attachments - quotation_attachments
        is_purchase_rep = request.env.user.has_group("employee_portal_suite.group_mr_purchase_rep")

        can_submit_accounting_docs = bool(
            accounting_attachments
            and rec.sudo().has_unsubmitted_accounting_docs()
        )

        return request.render("employee_portal_suite.portal_material_approval_detail", {
            "request_rec": rec,
            "attachments": attachments,
            "accounting_attachments": accounting_attachments,
            "quotation_attachments": quotation_attachments,
            "can_submit_accounting_docs": can_submit_accounting_docs,
            "is_purchase_rep": is_purchase_rep,
            "status_badge": _mr_status_badge,
        })


    # ---------------------------------------------------------
    # APPROVE
    # ---------------------------------------------------------
    @http.route("/my/employee/material/requests/approve", type="http", auth="user", website=True, csrf=True)
    def material_approve(self, **post):
        user = request.env.user
        rec = request.env["material.request"].sudo().browse(int(post.get("req_id")))
        comment = post.get("comment") or ""

        if not rec.exists():
            return request.redirect("/my")

        if rec.state == "purchase":
            rec.purchase_comment = comment
            rec.action_purchase()


        elif rec.state == "store":
            rec.store_comment = comment
            rec.action_store()

        elif rec.state == "project_manager":
            rec.project_manager_comment = comment
            rec.action_project_manager()

        elif rec.state == "director":
            rec.director_comment = comment
            rec.action_director()

        elif rec.state == "ceo":
            rec.ceo_comment = comment
            rec.action_ceo()

        return request.redirect("/my/employee/material/approvals")

    # ---------------------------------------------------------
    # REJECT
    # ---------------------------------------------------------
    @http.route("/my/employee/material/requests/reject", type="http", auth="user", website=True, csrf=True)
    def material_reject(self, **post):
        rec = request.env["material.request"].sudo().browse(int(post.get("req_id")))
        comment = (post.get("comment") or "").strip()

        if not rec.exists():
            return request.redirect("/my")

        # REQUIRE COMMENT
        if not comment:
            return request.redirect(f"/my/employee/material/approvals/{rec.id}")

        # assign comment
        if rec.state == "purchase":
            rec.purchase_comment = comment
        elif rec.state == "store":
            rec.store_comment = comment
        elif rec.state == "project_manager":
            rec.project_manager_comment = comment
        elif rec.state == "director":
            rec.director_comment = comment
        elif rec.state == "ceo":
            rec.ceo_comment = comment

        rec.sudo().action_reject()

        return request.redirect("/my/employee/material/approvals")

    # PDF MATERIAL REQUEST EXPORT
    @http.route("/my/employee/material/pdf/<int:req_id>", type="http", auth="user", website=True)
    def portal_material_request_pdf(self, req_id, **kw):

        rec = request.env["material.request"].sudo().browse(req_id)
        if not rec.exists():
            return request.not_found()

        if rec.state not in ["approved", "rejected"]:
            return request.redirect(f"/my/employee/material/approvals/{req_id}")

        # Load the report action
        report_action = request.env.ref(
            "employee_portal_suite.material_request_pdf"
        ).sudo()

        # Use Odoo's official report service (IMPORTANT)
        ReportService = request.env['ir.actions.report'].sudo()

        # Render PDF CORRECTLY
        pdf_content, content_type = ReportService._render_qweb_pdf(
            report_action.id, [rec.id]
        )

        headers = [
            ("Content-Type", "application/pdf"),
            ("Content-Length", len(pdf_content)),
            ("Content-Disposition", f'attachment; filename=\"{rec.name}.pdf\"'),
        ]

        return request.make_response(pdf_content, headers=headers)

    @http.route(
        "/my/employee/material/requests/set_clarification",
        type="http",
        auth="user",
        website=True,
        csrf=True,
    )
    def set_clarification(self, **post):

        rec = request.env["material.request"].sudo().browse(int(post.get("req_id")))

        if not rec.exists():
            return request.redirect("/my")

        # Security
        if not rec._can_toggle_clarification():
            return request.redirect(
                request.httprequest.referrer + "?clarify_error=1"
            )

        is_flagged = post.get("flag") == "on"

        rec.write({
            "needs_clarification": is_flagged,
            "clarification_stage": rec.state if is_flagged else False,
        })

        return request.redirect(request.httprequest.referrer)

    @http.route(
        "/my/employee/material/submit_docs_to_accounting",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def submit_docs_to_accounting(self, **post):
        user = request.env.user
        rec = request.env["material.request"].sudo().browse(int(post.get("req_id", 0)))

        if not rec.exists():
            return request.redirect("/my")

        if not user.has_group("employee_portal_suite.group_mr_purchase_rep"):
            return request.redirect("/my")

        if rec.state != "approved":
            return request.redirect(f"/my/employee/material/approvals/{rec.id}")

        if not rec.sudo().has_unsubmitted_accounting_docs():
            return request.redirect(f"/my/employee/material/approvals/{rec.id}")

        note = (post.get("accounting_docs_note") or "").strip()
        rec.sudo().action_submit_docs_to_accounting(note=note)
        return request.redirect(f"/my/employee/material/approvals/{rec.id}")

    # Attachment
    import base64

    @http.route(
        '/my/employee/material/attachment/upload',
        type='http',
        auth='user',
        website=True,
        methods=['POST']
    )
    def upload_material_attachment(self, **kw):

        req_id = int(kw.get("req_id", 0))
        tag = kw.get("attachment_tag", "General")

        rec = request.env["material.request"].sudo().browse(req_id)
        if not rec.exists():
            return request.not_found()

        category_by_tag = {
            "Accounting Documents": "invoice_submission",
            "Quotation Documents": "quotation",
        }
        category = category_by_tag.get(tag, "general")

        if category in ("invoice_submission", "quotation"):
            if not request.env.user.has_group("employee_portal_suite.group_mr_purchase_rep"):
                return request.redirect("/my")
        if category == "invoice_submission" and rec.state != "approved":
            return request.redirect(f"/my/employee/material/approvals/{rec.id}")

        files = request.httprequest.files.getlist("attachments")

        allowed_accounting_ext = (".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx")
        allowed_quotation_ext = (".pdf", ".jpg", ".jpeg", ".png", ".xls", ".xlsx", ".doc", ".docx")
        max_accounting_size = 10 * 1024 * 1024
        max_quotation_size = 10 * 1024 * 1024

        uploaded_names = []
        for f in files:
            if not f or f.filename.strip() == "":
                continue

            filename = f.filename.strip()
            if category == "invoice_submission" and not filename.lower().endswith(allowed_accounting_ext):
                continue
            if category == "quotation" and not filename.lower().endswith(allowed_quotation_ext):
                continue

            file_content = f.read()
            if category == "invoice_submission" and len(file_content) > max_accounting_size:
                continue
            if category == "quotation" and len(file_content) > max_quotation_size:
                continue

            request.env["ir.attachment"].sudo().create({
                "name": filename,
                "datas": base64.b64encode(file_content).decode(),   # REQUIRED
                "mimetype": f.mimetype,                             # RECOMMENDED
                "res_model": "material.request",
                "res_id": rec.id,
                "type": "binary",
                "description": tag,
                "public": True,   # ← THIS IS THE MAGIC FIX
            })
            uploaded_names.append(filename)

        if uploaded_names:
            names_text = ", ".join(uploaded_names)
            if category == "invoice_submission":
                rec.sudo().message_post(
                    body=_("Invoice document(s) uploaded for Accounting: %s") % names_text,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
            elif category == "quotation":
                rec.sudo()._compute_quotation_status()
                rec.sudo().message_post(
                    body=_("Quotation document(s) uploaded: %s") % names_text,
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )

        # Detect origin page (detail vs approval)
        came_from_approval = "/material/approvals/" in (request.httprequest.referrer or "")

        if came_from_approval:
            return request.redirect(f"/my/employee/material/approvals/{req_id}")
        else:
            return request.redirect(f"/my/employee/material/{req_id}")

    # Attachment Delete
    @http.route(
        '/my/employee/material/attachment/delete/<int:att_id>/<int:req_id>',
        type='http',
        auth='user',
        website=True,
    )
    def delete_material_attachment(self, att_id, req_id, **kw):

        att = request.env["ir.attachment"].sudo().browse(att_id)
        rec = request.env["material.request"].sudo().browse(req_id)
        if att.exists() and rec.exists():
            category = "invoice_submission" if (att.description or "") == "Accounting Documents" else "quotation" if (att.description or "") == "Quotation Documents" else "general"

            # Quotation and invoice submission files are managed by the Purchase Representative
            # from the portal. Deletion should behave like the original MR attachment delete,
            # but keep the related counters/status helpers consistent after unlink.
            if category in ("invoice_submission", "quotation") and not request.env.user.has_group("employee_portal_suite.group_mr_purchase_rep"):
                return request.redirect(f"/my/employee/material/approvals/{req_id}")

            att.unlink()

            if category == "invoice_submission":
                current_count = rec._get_accounting_attachment_count()
                if rec.accounting_docs_submitted_attachment_count > current_count:
                    rec.write({"accounting_docs_submitted_attachment_count": current_count})
                if current_count == 0 and rec.accounting_docs_status == "submitted":
                    rec.write({"accounting_docs_status": "pending"})
            elif category == "quotation":
                rec._compute_quotation_status()

        came_from_approval = "/material/approvals/" in (request.httprequest.referrer or "")

        if came_from_approval:
            return request.redirect(f"/my/employee/material/approvals/{req_id}")
        else:
            return request.redirect(f"/my/employee/material/{req_id}")

    @http.route('/my/employee/material/<int:request_id>/message', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def post_message(self, request_id, **post):
        record = request.env['material.request'].sudo().browse(request_id)
        message = (post.get('message') or '').strip()

        if not record.exists():
            return request.redirect('/my')

        if message:
            record.message_post(
                body=message,
                message_type='comment',
                subtype_xmlid='mail.mt_comment'
            )

        came_from_approval = "/material/approvals/" in (request.httprequest.referrer or "")

        if came_from_approval:
            return request.redirect(f'/my/employee/material/approvals/{request_id}')
        return request.redirect(f'/my/employee/material/{request_id}')