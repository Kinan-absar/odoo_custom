from odoo import http
from odoo.http import request

def _er_status_badge(rec):
    state = rec.state

    # APPROVED
    if state == "approved":
        return '<span class="badge bg-success">Fully Approved</span>'

    # REJECTED
    if state == "rejected":
        return '<span class="badge bg-danger">Rejected</span>'

    # PENDING STAGES
    stage_labels = {
        'manager': 'Pending Manager',
        'hr': 'Pending HR',
        'finance': 'Pending Finance',
        'ceo': 'Pending CEO',
    }

    if state in stage_labels:
        return f'<span class="badge bg-warning text-dark">{stage_labels[state]}</span>'

    return '<span class="badge bg-secondary">Unknown</span>'

class EmployeePortalRequests(http.Controller):

    

    # ---------------------------------------------------------
    # Helper
    # ---------------------------------------------------------
    def _get_employee(self):
        return request.env.user.employee_id

    # ---------------------------------------------------------
    # EMPLOYEE — LIST OWN REQUESTS
    # ---------------------------------------------------------
    @http.route('/my/employee/requests', type='http', auth='user', website=True)
    def portal_list(self, **kw):
        emp = self._get_employee()
        if not emp:
            return request.redirect('/my')

        requests = request.env['employee.request'].sudo().search([
            ('employee_id', '=', emp.id)
        ])

        return request.render("employee_portal_suite.employee_requests_page", {
            "requests": requests,
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
        })

    # ---------------------------------------------------------
    # EMPLOYEE — NEW FORM
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/new', type='http', auth='user', website=True)
    def portal_new(self, **kw):
        emp = self._get_employee()
        if not emp:
            return request.redirect('/my')

        return request.render("employee_portal_suite.employee_request_new_form")

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

        # Build vals
        vals = {
            'employee_id': emp.id,
            'request_date': post.get('request_date'),
            'request_type': req_type,
            'description': post.get('description'),
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

        # Allow only employee approval groups
        if not (
            user.has_group("employee_portal_suite.group_employee_portal_manager")
            or user.has_group("employee_portal_suite.group_employee_portal_hr")
            or user.has_group("employee_portal_suite.group_employee_portal_finance")
            or user.has_group("employee_portal_suite.group_employee_portal_ceo")
        ):
            return request.redirect('/my')

        emp = user.employee_id
        current_filter = kw.get("filter", "pending")

        # ---------------------------------------------------------
        # 1) PENDING LIST — requests waiting for THIS user
        # ---------------------------------------------------------
        pending_list = []

        for rec in EmployeeReq.search([
            ('state', 'in', ['manager', 'hr', 'finance', 'ceo'])
        ]):

            if rec.state == "manager" and user.has_group("employee_portal_suite.group_employee_portal_manager"):
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

        # ---------------------------------------------------------
        # 3) REJECTED LIST — requests user rejected
        # ---------------------------------------------------------
        rejected_list = EmployeeReq.search([
            ("state", "=", "rejected"),
            ("rejected_by", "=", user.id),
        ])

        # ---------------------------------------------------------
        # 4) ALL LIST
        # ---------------------------------------------------------
        all_reqs = list({*pending_list, *approved_list, *rejected_list})

        # ---------------------------------------------------------
        # 5) Apply filter
        # ---------------------------------------------------------
        shown_reqs = {
            "pending": pending_list,
            "approved": approved_list,
            "rejected": rejected_list,
            "all": all_reqs,
        }.get(current_filter, pending_list)

        return request.render("employee_portal_suite.portal_employee_approvals_list", {
            "pending_reqs": pending_list,
            "approved_reqs": approved_list,
            "rejected_reqs": rejected_list,
            "all_reqs": all_reqs,
            "shown_reqs": shown_reqs,
            "current_filter": current_filter,
            "status_badge": _er_status_badge,
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

        # Only managers/hr/finance/ceo
        if not (
            user.has_group("employee_portal_suite.group_employee_portal_manager")
            or user.has_group("employee_portal_suite.group_employee_portal_hr")
            or user.has_group("employee_portal_suite.group_employee_portal_finance")
            or user.has_group("employee_portal_suite.group_employee_portal_ceo")
        ):
            return request.redirect('/my')

        return request.render("employee_portal_suite.portal_manager_request_detail", {
            "request_rec": rec,
            "status_badge": _er_status_badge,
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

        if rec.state == "manager":
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
    # PORTAL REJECT (Manager / HR / Finance / CEO)
    # ---------------------------------------------------------
    @http.route('/my/employee/requests/reject', type='http', auth='user', website=True, csrf=True)
    def portal_reject(self, **post):
        req_id = int(post.get("req_id"))
        comment = (post.get("comment") or "").strip()
        user = request.env.user

        # REQUIRE REJECTION COMMENT
        if not comment:
            return request.redirect(f"/my/employee/requests/{req_id}")  # go back to detail page

        rec = request.env['employee.request'].sudo().browse(req_id)

        if not rec.exists():
            return request.redirect('/my/employee/approvals')

        # Save rejection comment in correct field
        if rec.state == 'manager' and rec.manager_id == user.employee_id:
            rec.manager_comment = comment

        elif rec.state == 'hr' and user.has_group('employee_portal_suite.group_employee_portal_hr'):
            rec.hr_comment = comment

        elif rec.state == 'finance' and user.has_group('employee_portal_suite.group_employee_portal_finance'):
            rec.finance_comment = comment

        elif rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'):
            rec.ceo_comment = comment

        # Now actually reject
        rec.sudo().action_reject()

        return request.redirect('/my/employee/approvals')
    