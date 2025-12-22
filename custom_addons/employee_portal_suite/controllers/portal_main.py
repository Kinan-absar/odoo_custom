from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal


class EmployeePortalMain(CustomerPortal):

    # ---------------------------------------------------------
    # EMPLOYEE PORTAL DASHBOARD (MAIN /my/employee)
    # ---------------------------------------------------------
    @http.route('/my/employee', type='http', auth='user', website=True)
    def employee_portal_dashboard(self, **kw):
        user = request.env.user
        employee = user.employee_id

        # ------------------------------------------------------
        # 1. My Employee Requests
        # ------------------------------------------------------
        my_request_count = request.env['employee.request'].sudo().search_count([
            ('employee_id', '=', employee.id)
        ])

        # ------------------------------------------------------
        # 2. My Material Requests
        # ------------------------------------------------------
        my_material_count = request.env['material.request'].sudo().search_count([
            ('employee_id.user_id', '=', user.id)
        ])

        # ------------------------------------------------------
        # 3. Employee Pending Approvals
        # ------------------------------------------------------
        employee_pending_count = 0

        pending_recs = request.env['employee.request'].sudo().search([
            ('state', 'in', ['manager', 'hr', 'finance', 'ceo'])
        ])

        for rec in pending_recs:

            # Manager approval (only if direct manager)
            if rec.state == 'manager' and user.has_group('employee_portal_suite.group_employee_portal_manager'):
                if rec.manager_id == employee:
                    employee_pending_count += 1

            # HR approval
            elif rec.state == 'hr' and user.has_group('employee_portal_suite.group_employee_portal_hr'):
                employee_pending_count += 1

            # Finance approval
            elif rec.state == 'finance' and user.has_group('employee_portal_suite.group_employee_portal_finance'):
                employee_pending_count += 1

            # CEO approval
            elif rec.state == 'ceo' and user.has_group('employee_portal_suite.group_employee_portal_ceo'):
                employee_pending_count += 1

        # ------------------------------------------------------
        # 4. Material Pending Approvals
        # ------------------------------------------------------
        if user.has_group('employee_portal_suite.group_mr_purchase_rep'):
            stage_domain = [('state', '=', 'purchase')]
        elif user.has_group('employee_portal_suite.group_mr_store_manager'):
            stage_domain = [('state', '=', 'store')]
        elif user.has_group('employee_portal_suite.group_mr_project_manager'):
            stage_domain = [('state', '=', 'project_manager')]
        elif user.has_group('employee_portal_suite.group_mr_projects_director'):
            stage_domain = [('state', '=', 'director')]
        elif user.has_group('employee_portal_suite.group_employee_portal_ceo'):
            stage_domain = [('state', '=', 'ceo')]
        else:
            stage_domain = [('id', '=', 0)]  # this user has no MR approval role

        material_pending_count = request.env['material.request'].sudo().search_count(stage_domain)
        # -------------------------------
        # 4. Documents to Sign
        # -------------------------------
        pending_sign_count = 0
        if "sign.request.item" in request.env:
            pending_sign_count = request.env["sign.request.item"].sudo().search_count([
                ('partner_id', '=', user.partner_id.id),
                ('state', '=', 'sent')
            ])
        # ------------------------------------------------------
        # Render
        # ------------------------------------------------------
        return request.render("employee_portal_suite.employee_portal_dashboard", {
            "my_request_count": my_request_count,
            "my_material_count": my_material_count,
            "employee_pending_count": employee_pending_count,
            "material_pending_count": material_pending_count,
            "pending_sign_count": pending_sign_count,
        })
