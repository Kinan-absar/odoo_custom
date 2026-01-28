from odoo import http
from odoo.http import request


class EmployeePortalMobileAuth(http.Controller):

    @http.route(
        "/api/mobile/login",
        type="http",
        auth="none",
        csrf=False,
        methods=["POST"]
    )
    def mobile_login(self, **kwargs):
        email = kwargs.get("email")
        password = kwargs.get("password")

        if not email or not password:
            return request.make_json_response(
                {"error": "Missing credentials"}, 400
            )

        uid = request.session.authenticate(
            request.env.cr.dbname,
            email,
            password
        )


        if not uid:
            return request.make_json_response(
                {"error": "Invalid email or password"}, 401
            )

        user = request.env["res.users"].sudo().browse(uid)

        if not user.has_group("base.group_portal"):
            return request.make_json_response(
                {"error": "Access denied"}, 403
            )

        employee = request.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)], limit=1
        )

        if not employee:
            return request.make_json_response(
                {"error": "No employee linked"}, 404
            )

        role = "manager" if user.has_group(
            "employee_portal_suite.group_portal_manager"
        ) else "employee"

        return request.make_json_response({
            "token": "fake-token-dev",
            "role": role,
            "employee_id": employee.id,
        })
