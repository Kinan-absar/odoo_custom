from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError, ValidationError


class EmployeePortalMain(CustomerPortal):

    def _model_exists(self, model_name):
        """Return True only when an optional model is loaded in the current DB registry."""
        return model_name in request.env

    def _safe_has_group(self, xmlid):
        """Avoid errors when an optional module group XMLID is not installed."""
        if not request.env.ref(xmlid, raise_if_not_found=False):
            return False
        return request.env.user.has_group(xmlid)

    def _construction_portal_available(self):
        """Construction Contract Management is optional for Employee Portal Suite."""
        required_models = (
            'construction.contract',
            'construction.ipc',
            'construction.variation',
            'construction.measurement',
        )
        return all(self._model_exists(model) for model in required_models)

    def _portal_visible_contract_domain(self):
        user = request.env.user
        if user:
            return ['|', ('portal_visibility_restricted', '=', False), ('portal_employee_ids.user_id', '=', user.id)]
        return [('portal_visibility_restricted', '=', False)]

    def _portal_visible_contracts(self):
        if not self._model_exists('construction.contract'):
            return request.env['project.project'].browse([])
        return request.env['construction.contract'].sudo().search(self._portal_visible_contract_domain())

    def _portal_visible_contract_ids(self):
        if not self._model_exists('construction.contract'):
            return []
        return self._portal_visible_contracts().ids

    # ---------------------------------------------------------
    # EMPLOYEE PORTAL DASHBOARD (MAIN /my/employee)
    # ---------------------------------------------------------
    @http.route('/my/employee', type='http', auth='user', website=True)
    def employee_portal_dashboard(self, **kw):
        # Attendance-only users go straight to the attendance page.
        if request.env.user.has_group('employee_portal_suite.group_attendance_only'):
            return request.redirect('/my/employee/attendance')

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
        # 3-5, 7-8. Pending approvals, signatures, and reports —
        # all sourced from the shared notification summary so the
        # dashboard cards and the header bell never disagree.
        # ------------------------------------------------------
        notif_summary = request.env['portal.report.seen'].sudo()._get_notification_summary(user)

        employee_pending_count = notif_summary.get('er_approval', {}).get('count', 0)
        new_employee_pending_count = notif_summary.get('er_approval', {}).get('new', 0)
        material_pending_count = notif_summary.get('mr_approval', {}).get('count', 0)
        new_material_pending_count = notif_summary.get('mr_approval', {}).get('new', 0)
        pending_sign_count = notif_summary.get('sign_request', {}).get('count', 0)
        new_pending_sign_count = notif_summary.get('sign_request', {}).get('new', 0)
        salary_report_count = notif_summary.get('salary_report', {}).get('count', 0)
        new_salary_report_count = notif_summary.get('salary_report', {}).get('new', 0)
        portal_report_count = notif_summary.get('portal_report', {}).get('count', 0)
        new_portal_report_count = notif_summary.get('portal_report', {}).get('new', 0)

        # -------------------------------
        # 6. Construction Counts
        # -------------------------------
        contract_count = 0
        ipc_count = 0
        variation_count = 0
        measurement_count = 0
        
        if self._construction_portal_available() and request.env['construction.contract'].check_access_rights('read', raise_exception=False):
            contract_count = request.env['construction.contract'].search_count([])
            ipc_count = request.env['construction.ipc'].search_count([])
            variation_count = request.env['construction.variation'].search_count([])
            measurement_count = request.env['construction.measurement'].search_count([])
        show_construction_cards = self._construction_portal_available() and self._safe_has_group('construction_contract_management.group_construction_portal')

        # ------------------------------------------------------
        # 9. Recent Activities
        # ------------------------------------------------------
        from itertools import chain

        EmployeeRequest = request.env['employee.request'].sudo()
        MaterialRequest = request.env['material.request'].sudo()

        recent_employee = EmployeeRequest.search(
            [('employee_id', '=', employee.id)],
            order='create_date desc',
            limit=5
        )

        recent_material = MaterialRequest.search(
            [('employee_id.user_id', '=', user.id)],
            order='create_date desc',
            limit=5
        )

        recent_activities = list(chain(recent_employee, recent_material))
        recent_activities = sorted(
            recent_activities,
            key=lambda r: r.create_date or r.write_date,
            reverse=True
        )[:6]

        # ------------------------------------------------------
        # 9. Attendance Status
        # ------------------------------------------------------
        can_use_attendance = request.env.user.has_group(
            'employee_portal_suite.group_portal_attendance_user'
        )
        attendance_checked_in = False
        if employee and can_use_attendance:
            open_att = request.env['hr.attendance'].sudo().search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False),
            ], limit=1)
            attendance_checked_in = bool(open_att)

        # ------------------------------------------------------
        # Render
        # ------------------------------------------------------
        return request.render("employee_portal_suite.employee_portal_dashboard", {
            "my_request_count": my_request_count,
            "my_material_count": my_material_count,
            "employee_pending_count": employee_pending_count,
            "new_employee_pending_count": new_employee_pending_count,
            "material_pending_count": material_pending_count,
            "new_material_pending_count": new_material_pending_count,
            "pending_sign_count": pending_sign_count,
            "new_pending_sign_count": new_pending_sign_count,
            "salary_report_count": salary_report_count,
            "new_salary_report_count": new_salary_report_count,
            "portal_report_count": portal_report_count,
            "new_portal_report_count": new_portal_report_count,
            "recent_activities": recent_activities,
            "contract_count": contract_count,
            "ipc_count": ipc_count,
            "variation_count": variation_count,
            "measurement_count": measurement_count,
            "show_construction_cards": show_construction_cards,
            "attendance_checked_in": attendance_checked_in,
            "can_use_attendance": can_use_attendance,
        })
