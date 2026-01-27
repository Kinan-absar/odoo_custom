from odoo import http
from odoo.http import request


class EmployeePortalMobileAuth(http.Controller):

    @http.route(
        "/api/mobile/login",
        type="json",
        auth="none",
        csrf=False
    )
    def mobile_login(self, email=None, password=None):
        if not email or not password:
            return {"error": "Missing credentials"}

        uid = request.session.authenticate(
            request.db, email, password
        )

        if not uid:
            return {"error": "Invalid email or password"}

        user = request.env["res.users"].sudo().browse(uid)

        # SAFETY: allow portal users only
        if not user.has_group("base.group_portal"):
            return {"error": "Access denied"}

        # Link to employee
        employee = request.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)],
            limit=1
        )

        if not employee:
            return {"error": "No employee linked to user"}

        # TEMP: fake token (safe for staging)
        role = "employee"

        # If you already have a manager group in your module, use it
        if user.has_group("employee_portal_suite.group_portal_manager"):
            role = "manager"

        return {
            "token": "fake-token-staging",
            "role": role,
            "employee_id": employee.id,
        }
