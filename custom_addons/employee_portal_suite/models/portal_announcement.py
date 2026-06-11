from odoo import models, fields, api
from datetime import date


class PortalAnnouncement(models.Model):
    _name = "portal.announcement"
    _description = "Portal Announcement"
    _order = "sequence desc, id desc"

    name = fields.Char(required=True)
    message = fields.Html(required=True)

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    start_date = fields.Date()
    end_date = fields.Date()

    target = fields.Selection([
        ("portal", "Employee Portal Only"),
        ("backend", "Internal Backend Only"),
        ("both", "Employee Portal + Internal Backend"),
    ], default="both", required=True,
        help="Choose where this announcement should be displayed."
    )

    group_ids = fields.Many2many(
        "res.groups",
        string="Visible To Groups",
        help="If empty, visible to all users in the selected target."
    )

    attachment_ids = fields.Many2many(
        "ir.attachment",
        "portal_announcement_ir_attachment_rel",
        "announcement_id",
        "attachment_id",
        string="Attachments",
        help="Upload PDF or image files to show with this announcement in the employee portal."
    )

    color = fields.Selection([
        ('primary', 'Blue'),
        ('success', 'Green'),
        ('warning', 'Yellow'),
        ('danger', 'Red'),
    ], default='primary')

    @api.model
    def _get_visible_announcements_for_current_user(self, target="backend", limit=0):
        """Return active announcements visible to the current user and target."""
        today = fields.Date.context_today(self)
        domain = [
            ("active", "=", True),
            "|", ("start_date", "=", False), ("start_date", "<=", today),
            "|", ("end_date", "=", False), ("end_date", ">=", today),
            ("target", "in", [target, "both"]),
        ]
        # limit=0 means no limit in Odoo search
        announcements = self.sudo().search(domain, order="sequence desc, id desc", limit=limit or False)

        user_groups = self.env.user.groups_id
        return announcements.filtered(lambda ann: not ann.group_ids or bool(user_groups & ann.group_ids))

    def _user_can_access(self, user, target="portal"):
        """Security helper for announcement attachment preview/download routes."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if not self.active:
            return False
        if self.start_date and self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        if self.target not in (target, "both"):
            return False
        if self.group_ids and not bool(user.groups_id & self.group_ids):
            return False
        return True

    @api.model
    def get_backend_announcements(self):
        """Payload used by the backend web client notification service."""
        color_to_type = {
            "primary": "info",
            "success": "success",
            "warning": "warning",
            "danger": "danger",
        }
        result = []
        for ann in self._get_visible_announcements_for_current_user(target="backend"):
            result.append({
                "id": ann.id,
                "title": ann.name,
                "message": ann.message or "",
                "type": color_to_type.get(ann.color, "info"),
            })
        return result
