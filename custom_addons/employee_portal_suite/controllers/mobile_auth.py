from odoo import http
from odoo.http import request

class EmployeePortalMobileAuth(http.Controller):

    @http.route(
        "/api/mobile/login",
        type="json",
        auth="none",
        csrf=False
    )
    def mobile_login(self, **params):
        email = params.get("email")
        password = params.get("password")

        if not email or not password:
            return {"error": "Missing credentials"}

        uid = request.session.authenticate(
            request.env.cr.dbname,
            email,
            password
        )

        if not uid:
            return {"error": "Invalid email or password"}

        user = request.env["res.users"].sudo().browse(uid)

        if not user.has_group("base.group_portal"):
            return {"error": "Access denied"}

        employee = request.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)],
            limit=1
        )

        if not employee:
            return {"error": "No employee linked"}

        role = "employee"
        if user.has_group("employee_portal_suite.group_portal_manager"):
            role = "manager"

        return {
            "token": "fake-token-dev",
            "role": role,
            "employee_id": employee.id,
        }
