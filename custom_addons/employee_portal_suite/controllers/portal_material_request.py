from odoo import http
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

        records = request.env["material.request"].sudo().search([
            ("employee_id", "=", emp.id)
        ])

        # Pass the same badge renderer used in approver views
        return request.render("employee_portal_suite.employee_material_requests_page", {
            "requests": records,
            "status_badge": _mr_status_badge,
        })


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

        return request.render("employee_portal_suite.employee_material_request_new_form", {
            "uoms": uoms,
        })

    # ---------------------------------------------------------
    # CREATE REQUEST
    # ---------------------------------------------------------
    @http.route("/my/employee/material/create", type="http", auth="user", website=True, csrf=True)
    def material_create(self, **post):
        emp = self._employee()
        if not emp:
            return request.redirect("/my")

        # Create main request
        rec = request.env["material.request"].sudo().create({
            "employee_id": emp.id,
            "worksite": post.get("worksite"),
            "delivery_date": post.get("delivery_date"),
        })

        # Lines
        for i in range(20):
            name = post.get(f"item_name_{i}")
            qty  = post.get(f"qty_required_{i}")
            uom  = post.get(f"uom_id_{i}")

            if not name:
                continue

            request.env["material.request.line"].sudo().create({
                "request_id": rec.id,
                "item_name": name,
                "qty_required": qty or 0,
                "uom_id": int(uom) if uom else False,
            })

        rec.sudo().action_submit()
        # --- SAVE ATTACHMENTS FROM NEW FORM ---
        files = request.httprequest.files.getlist("attachments")
        tag = post.get("attachment_tag") or "General"

        for f in files:
            if not f or f.filename.strip() == "":
                continue

            file_content = f.read()

            request.env["ir.attachment"].sudo().create({
                "name": f.filename,
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

        current_filter = kw.get("filter", "pending")

        # ---------------------------------------------------------
        # 1) PENDING LIST — currently waiting for THIS user
        # ---------------------------------------------------------
        pending_list = []

        stage_group_map = {
            "purchase": "employee_portal_suite.group_mr_purchase_rep",
            "store": "employee_portal_suite.group_mr_store_manager",
            "project_manager": "employee_portal_suite.group_mr_project_manager",
            "director": "employee_portal_suite.group_mr_projects_director",
            "ceo": "employee_portal_suite.group_employee_portal_ceo",
        }

        for rec in Material.search([("state", "in", list(stage_group_map.keys()))]):
            g = stage_group_map.get(rec.state)
            if g and user.has_group(g):
                pending_list.append(rec)

        # ---------------------------------------------------------
        # 2) APPROVED LIST — ANY request user approved at any stage
        # ---------------------------------------------------------
        approved_list = Material.search([
            "|", "|", "|", "|",
            ("purchase_approved_by", "=", user.id),
            ("store_approved_by", "=", user.id),
            ("project_manager_approved_by", "=", user.id),
            ("director_approved_by", "=", user.id),
            ("ceo_approved_by", "=", user.id),
        ])

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

        return request.render("employee_portal_suite.portal_material_approvals_list", {
            "pending_reqs": pending_list,
            "approved_reqs": approved_list,
            "rejected_reqs": rejected_list,
            "all_reqs": all_reqs,
            "shown_reqs": shown_reqs,
            "current_filter": current_filter,
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

        attachments = request.env["ir.attachment"].sudo().search([
            ("res_model", "=", "material.request"),
            ("res_id", "=", rec.id)
        ])

        return request.render("employee_portal_suite.portal_material_approval_detail", {
            "request_rec": rec,
            "attachments": attachments,
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

        files = request.httprequest.files.getlist("attachments")

        for f in files:
            if not f or f.filename.strip() == "":
                continue

            file_content = f.read()
            

            request.env["ir.attachment"].sudo().create({
                "name": f.filename,
                "datas": base64.b64encode(file_content).decode(),   # REQUIRED
                "mimetype": f.mimetype,                             # RECOMMENDED
                "res_model": "material.request",
                "res_id": rec.id,
                "type": "binary",
                "description": tag,
                "public": True,   # ← THIS IS THE MAGIC FIX
            })

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
        if att.exists():
            att.unlink()

        came_from_approval = "/material/approvals/" in (request.httprequest.referrer or "")

        if came_from_approval:
            return request.redirect(f"/my/employee/material/approvals/{req_id}")
        else:
            return request.redirect(f"/my/employee/material/{req_id}")
