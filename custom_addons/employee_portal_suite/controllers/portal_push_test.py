import logging

from markupsafe import Markup

from odoo import _, http
from odoo.http import request


_logger = logging.getLogger(__name__)


class EmployeePortalPushTest(http.Controller):
    """Small diagnostic endpoint for testing Odoo's native notification path.

    This intentionally uses ``mail.thread.message_notify`` instead of a custom
    push provider. If Odoo has registered the portal user's mobile/PWA device,
    the standard mail/web-push stack is responsible for delivering the push.
    """

    @http.route(
        "/my/employee/test-push-notification",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def test_portal_push_notification(self, **post):
        user = request.env.user
        partner = user.partner_id

        if not partner:
            return request.redirect("/my/employee?push_test=no_partner")

        notification_type = getattr(user, "notification_type", "unknown") or "unknown"
        body = Markup(
            "<p><strong>Employee Portal notification test</strong></p>"
            "<p>This message was sent through Odoo's native notification "
            "system to test mobile/PWA push delivery for a portal user.</p>"
        )

        try:
            request.env["mail.thread"].sudo().message_notify(
                partner_ids=[partner.id],
                subject=_("Employee Portal push test"),
                body=body,
                model_description=_("Employee Portal"),
                force_send=True,
            )
        except Exception:
            _logger.exception("Portal push test notification failed for user %s", user.id)
            request.env.cr.rollback()
            return request.redirect(
                "/my/employee?push_test=error&notification_type=%s" % notification_type
            )

        return request.redirect(
            "/my/employee?push_test=sent&notification_type=%s" % notification_type
        )
