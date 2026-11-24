from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    employees = env["hr.employee"].search([("user_id.share", "=", True)])
    portal_users = employees.user_id
    for group in employees._employee_portal_base_groups():
        users_to_remove = group.users & portal_users
        if users_to_remove:
            group.write({"users": [(3, user.id) for user in users_to_remove]})

    channels = env["discuss.channel"].search([("is_employee_portal_channel", "=", True)])
    # Remove old employee-workspace memberships only from channels this module marked.
    memberships = channels.channel_member_ids.filtered(
        lambda member: member.partner_id in portal_users.partner_id
    )
    memberships.with_context(skip_employee_portal_channel_sync=True).unlink()
    channels.with_context(skip_employee_portal_channel_sync=True).write({
        "employee_portal_access": "disabled",
        "allow_public_upload": False,
    })

    # Revoke public flags and old links for these internal-only documents.
    env["ir.attachment"].search([
        ("res_model", "in", ["material.request", "employee.request"]),
        "|", ("public", "=", True), ("access_token", "!=", False),
    ]).write({"public": False, "access_token": False})
