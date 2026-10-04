from odoo import http
from odoo.http import request
from markupsafe import Markup, escape

def _er_status_badge(rec):
    state = rec.state

    # APPROVED
    if state == "approved":
        return Markup('<span class="badge bg-success">Fully Approved</span>')

    # REJECTED WITH STAGE
    if state == "rejected":
        stage_labels = {
            'manager': 'Manager',
            'hr': 'HR',
            'finance': 'Finance',
            'ceo': 'CEO',
        }

        if rec.state_before_reject == 'workflow':
            rejected_line = rec.approval_line_ids.filtered(lambda l: l.state == 'rejected')[:1]
            lbl = rejected_line.name if rejected_line else 'Workflow'
        else:
            lbl = stage_labels.get(rec.state_before_reject, "Unknown Stage")

        return Markup('<span class="badge bg-danger">Rejected — %s Stage</span>') % escape(lbl)
    # RETURNED FOR CORRECTION
    if state == 'returned':
        line = rec.approval_line_ids.filtered(lambda l: l.state == 'returned')[:1]
        label = line.name if line else 'Workflow'
        return Markup('<span class="badge bg-info text-dark">Returned for Correction — %s</span>') % escape(label)

    # CONFIGURABLE WORKFLOW
    if state == 'workflow':
        step = rec.current_approval_line_id
        label = step.name if step else 'Workflow Approval'
        return Markup('<span class="badge bg-warning text-dark">Pending — %s</span>') % escape(label)

    # PENDING STAGES
    stage_labels = {
        'manager': 'Pending Manager',
        'hr': 'Pending HR',
        'finance': 'Pending Finance',
        'ceo': 'Pending CEO',
    }

    if state in stage_labels:
        return Markup('<span class="badge bg-warning text-dark">%s</span>') % escape(stage_labels[state])

    return Markup('<span class="badge bg-secondary">Unknown</span>')

class EmployeePortalRequests(http.Controller):

    

    # ---------------------------------------------------------
    # Helper
    # ---------------------------------------------------------
    def _get_employee(self):
        user = request.env.user
        return user.employee_id if user.share else request.env['hr.employee']

    # ---------------------------------------------------------
    # EMPLOYEE — LIST OWN REQUESTS
    # ---------------------------------------------------------
    @http.route('/my/employee/requests', type='http', auth='user', website=True)
    def portal_list(self, **kw):
        emp = self._get_employee()
        if not emp:
            return request.redirect('/my')

        search = kw.get('search', '').strip()

        domain = [
            ('employee_id', '=', emp.id)
        ]

        if search:
            domain.append(('name', 'ilike', search))

        requests = request.env['employee.request'].sudo().search(
            domain,
            order="create_date desc"
        )

        return request.render("employee_portal_suite.employee_requests_page", {
            "requests": requests,
            "search": search,
            "status_badge": _er_status_badge,
        })



    # ---------------------------------------------------------
    # EMPLOYEE — VIEW SINGLE REQUEST
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/<int:req_id>', type='http', auth='user', website=True)
    def portal_detail(self, req_id, **kw):
        emp = self._get_employee()
        rec = request.env['employee.request'].sudo().browse(req_id)

        if not emp or rec.employee_id != emp:
            return request.redirect('/my')

        return request.render("employee_portal_suite.employee_request_detail_page", {
            "request_rec": rec,
            "status_badge": _er_status_badge,
        })

    # ---------------------------------------------------------
    # EMPLOYEE — NEW FORM
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/new', type='http', auth='user', website=True)
    def portal_new(self, **kw):
        emp = self._get_employee()
        if not emp:
            return request.redirect('/my')

        projects = emp.sudo()._get_material_request_projects()
        return request.render("employee_portal_suite.employee_request_new_form", {
            "projects": projects,
            "single_project": projects[:1] if len(projects) == 1 else False,
        })

    # ---------------------------------------------------------
    # EMPLOYEE — CREATE REQUEST
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/create', type='http', auth='user', website=True, csrf=True)
    def portal_create(self, **post):
        emp = self._get_employee()
        if not emp:
            return request.redirect('/my')

        # Clean mapping
        mapping = {
            "leave": "leave",
            "housing": "housing",
            "advance": "advance",
            "travel": "travel",
            "training": "training",
            "medical": "medical",
            "vacation_settlement": "vacation_settlement",
            "asset": "asset",
            "letter": "letter",
            "bank": "bank",
            "transfer": "transfer",
            "exit": "exit",
            "other": "other",
        }
        req_type = mapping.get(post.get("request_type"), "other")

        projects = emp.sudo()._get_material_request_projects()
        project_id = int(post.get('project_id') or 0)
        selected_project = request.env['project.project'].sudo().browse(project_id)
        if not selected_project.exists() or selected_project not in projects:
            return request.render('employee_portal_suite.employee_request_new_form', {
                'projects': projects,
                'single_project': projects[:1] if len(projects) == 1 else False,
                'error_message': _('Please select one of the projects assigned to your work location.'),
            })

        # Build vals
        vals = {
            'employee_id': emp.id,
            'request_date': post.get('request_date'),
            'request_type': req_type,
            'description': post.get('description'),
            'project_id': selected_project.id,
        }

        # Leave fields
        if req_type == "leave":
            vals['leave_from'] = post.get('leave_from') or False
            vals['leave_to']   = post.get('leave_to') or False

        new_rec = request.env['employee.request'].sudo().create(vals)
        # Auto-submit the request (no backend user needed)
        new_rec.sudo().action_submit()
        return request.redirect(f"/my/employee/requests/{new_rec.id}")


    # ---------------------------------------------------------
    # MANAGER — APPROVAL LIST
    # ---------------------------------------------------------
    @http.route('/my/employee/approvals', type='http', auth='user', website=True)
    def employee_approvals(self, **kw):
        user = request.env.user
        EmployeeReq = request.env['employee.request'].sudo()

        has_dynamic_approval = request.env['employee.portal.workflow.approval.line'].sudo().user_has_approval_area_access(
            user, 'employee_request'
        )

        # Allow employee approval groups or a specifically assigned dynamic approver
        if not (
            user.has_group("employee_portal_suite.group_employee_portal_manager")
            or user.has_group("employee_portal_suite.group_employee_portal_hr")
            or user.has_group("employee_portal_suite.group_employee_portal_finance")
            or user.has_group("employee_portal_suite.group_employee_portal_ceo")
            or user.has_group("employee_portal_suite.group_employee_portal_superadmin")
            or has_dynamic_approval
        ):
            return request.redirect('/my')

        emp = user.employee_id
        filter_cards = request.env['employee.portal.request.filter.card'].sudo().search([
            ('request_area', '=', 'employee_request'), ('active', '=', True)
        ], order='sequence,id')
        allowed_filters = filter_cards.mapped('filter_key') or ['pending']
        current_filter = kw.get("filter") or allowed_filters[0]
        if current_filter not in allowed_filters:
            current_filter = allowed_filters[0]
        search = kw.get("search")

        # ---------------------------------------------------------
        # 1) PENDING LIST — requests waiting for THIS user
        # ---------------------------------------------------------
        pending_list = []

        for rec in EmployeeReq.search([
            ('state', 'in', ['workflow', 'manager', 'hr', 'finance', 'ceo'])
        ]):

            if rec.state == 'workflow':
                if rec._portal_can_approve(user):
                    pending_list.append(rec)

            elif user.has_group("employee_portal_suite.group_employee_portal_superadmin"):
                pending_list.append(rec)

            elif rec.state == "manager" and user.has_group("employee_portal_suite.group_employee_portal_manager"):
                if rec.manager_id == emp:
                    pending_list.append(rec)

            elif rec.state == "hr" and user.has_group("employee_portal_suite.group_employee_portal_hr"):
                pending_list.append(rec)

            elif rec.state == "finance" and user.has_group("employee_portal_suite.group_employee_portal_finance"):
                pending_list.append(rec)

            elif rec.state == "ceo" and user.has_group("employee_portal_suite.group_employee_portal_ceo"):
                pending_list.append(rec)

        # ---------------------------------------------------------
        # 2) APPROVED LIST — requests user approved
        # ---------------------------------------------------------
        approved_list = EmployeeReq.search([
            "|", "|", "|",
            ("manager_approved_by", "=", user.id),
            ("hr_approved_by", "=", user.id),
            ("finance_approved_by", "=", user.id),
            ("ceo_approved_by", "=", user.id),
        ])
        dynamic_approved = EmployeeReq.search([('approval_line_ids.approved_by', '=', user.id)], order='id desc')
        approved_list = EmployeeReq.browse(list(dict.fromkeys(approved_list.ids + dynamic_approved.ids)))

        # ---------------------------------------------------------
        # 3) REJECTED LIST — requests user rejected
        # ---------------------------------------------------------
        rejected_list = EmployeeReq.search([
            ("state", "=", "rejected"),
            ("rejected_by", "=", user.id),
        ])

        # ---------------------------------------------------------
        # 4) ALL LIST — all records visible through the UNION of roles
        # ---------------------------------------------------------
        visibility_domain = EmployeeReq._portal_visibility_domain(user)
        all_reqs = EmployeeReq.search(visibility_domain, order="id desc")

        # ---------------------------------------------------------
        # 5) Apply filter
        # ---------------------------------------------------------
        shown_reqs = {
            "pending": pending_list,
            "approved": approved_list,
            "rejected": rejected_list,
            "all": all_reqs,
        }.get(current_filter, pending_list)
        # ---------------------------------------------------------
        # 6) APPLY SEARCH (by request number only)
        # ---------------------------------------------------------
        if search:
            shown_reqs = [r for r in shown_reqs if search.lower() in (r.name or "").lower()]

        # Clear the "new approval" badge on the dashboard/header bell now that
        # the user has opened the approvals list.
        request.env['portal.report.seen'].sudo()._mark_seen(user.id, 'er_approval')

        return request.render("employee_portal_suite.portal_employee_approvals_list", {
            "pending_reqs": pending_list,
            "approved_reqs": approved_list,
            "rejected_reqs": rejected_list,
            "all_reqs": all_reqs,
            "shown_reqs": shown_reqs,
            "current_filter": current_filter,
            "filter_cards": filter_cards,
            "status_badge": _er_status_badge,
            "search": search,   # 👈 ADD THIS
        })


    # ---------------------------------------------------------
    # MANAGER — APPROVAL DETAIL
    # ---------------------------------------------------------
    @http.route('/my/employee/approvals/<int:req_id>', type='http', auth='user', website=True)
    def portal_approval_detail(self, req_id, **kw):
        user = request.env.user
        rec = request.env['employee.request'].sudo().browse(req_id)

        if not rec.exists():
            return request.redirect('/my')

        # Visibility is additive across all assigned roles.
        if not rec._portal_can_view(user):
            return request.redirect('/my/employee/approvals')

        return request.render("employee_portal_suite.portal_manager_request_detail", {
            "request_rec": rec,
            "status_badge": _er_status_badge,
            "can_approve": rec._portal_can_approve(user),
        })

   # ---------------------------------------------------------
# PORTAL APPROVE (Manager / HR / Finance / CEO)
# ---------------------------------------------------------
    @http.route('/my/employee/requests/approve', type='http', auth='user', website=True, csrf=True)
    def portal_approve(self, **post):
        req_id = int(post.get("req_id"))
        comment = post.get("comment") or ""
        user = request.env.user

        rec = request.env['employee.request'].sudo().browse(req_id)

        if not rec.exists():
            return request.redirect('/my/employee/approvals')

        if not rec._portal_can_approve(user):
            return request.redirect(f"/my/employee/approvals/{rec.id}")

        if rec.state == 'workflow':
            if rec.current_approval_line_id:
                rec.current_approval_line_id.sudo().comment = post.get('comment') or False
            rec.with_context(workflow_actor_user_id=user.id).action_workflow_approve()

        elif rec.state == "manager":
            rec.manager_comment = comment
            rec.action_manager_approve()

        elif rec.state == "hr":
            rec.hr_comment = comment
            rec.action_hr_approve()

        elif rec.state == "finance":
            rec.finance_comment = comment
            rec.action_finance_approve()

        elif rec.state == "ceo":
            rec.ceo_comment = comment
            rec.action_ceo_approve()


        return request.redirect('/my/employee/approvals')

    # ---------------------------------------------------------
    # PORTAL RETURN FOR CORRECTION (configurable workflow only)
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/return', type='http', auth='user', website=True, csrf=True)
    def portal_return_for_correction(self, **post):
        req_id = int(post.get('req_id'))
        reason = (post.get('reason') or '').strip()
        user = request.env.user

        rec = request.env['employee.request'].sudo().browse(req_id)
        if not rec.exists():
            return request.redirect('/my/employee/approvals')

        if rec.state != 'workflow' or not rec._portal_can_approve(user):
            return request.redirect(f'/my/employee/approvals/{rec.id}')

        if not reason:
            return request.redirect(f'/my/employee/approvals/{rec.id}')

        rec.with_context(workflow_actor_user_id=user.id)._workflow_return_confirm(reason)
        return request.redirect('/my/employee/approvals')


        # ---------------------------------------------------------
    # PORTAL REJECT (Manager / HR / Finance / CEO)
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/reject', type='http', auth='user', website=True, csrf=True)
    def portal_reject(self, **post):
        req_id = int(post.get("req_id"))
        comment = (post.get("comment") or "").strip()
        user = request.env.user

        # REQUIRE REJECTION COMMENT
        if not comment:
            return request.redirect(f"/my/employee/approvals/{req_id}")

        rec = request.env['employee.request'].sudo().browse(req_id)

        if not rec.exists():
            return request.redirect('/my/employee/approvals')

        if not rec._portal_can_approve(user):
            return request.redirect(f"/my/employee/approvals/{rec.id}")

        # Authorization was already checked above; save the comment for the current stage.
        # This also supports the explicit Super Administrator override.
        if rec.state == 'workflow':
            if rec.current_approval_line_id:
                rec.current_approval_line_id.sudo().comment = comment
            rec.with_context(workflow_actor_user_id=user.id).action_workflow_reject()
            return request.redirect('/my/employee/approvals')
        elif rec.state == 'manager':
            rec.manager_comment = comment
        elif rec.state == 'hr':
            rec.hr_comment = comment
        elif rec.state == 'finance':
            rec.finance_comment = comment
        elif rec.state == 'ceo':
            rec.ceo_comment = comment

        # Now actually reject
        rec.sudo().action_reject()

        return request.redirect('/my/employee/approvals')
    