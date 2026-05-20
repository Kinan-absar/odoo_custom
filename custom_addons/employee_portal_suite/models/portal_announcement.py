from odoo import models, fields, api
from odoo.tools import html2plaintext
from datetime import date
import re



class PortalAnnouncement(models.Model):
    _name = "portal.announcement"
    _description = "Portal Announcement"
    _order = "sequence desc, id desc"

    name = fields.Char(required=True)
    message = fields.Text(required=True)

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

    color = fields.Selection([
        ('primary', 'Blue'),
        ('success', 'Green'),
        ('warning', 'Yellow'),
        ('danger', 'Red'),
    ], default='primary')


    @api.model
    def _get_visible_announcements_for_current_user(self, target="backend", limit=5):
        """Return active announcements visible to the current user and target."""
        today = fields.Date.context_today(self)
        announcements = self.sudo().search([
            ("active", "=", True),
            "|", ("start_date", "=", False), ("start_date", "<=", today),
            "|", ("end_date", "=", False), ("end_date", ">=", today),
            ("target", "in", [target, "both"]),
        ], order="sequence desc, id desc", limit=limit)

        user_groups = self.env.user.groups_id
        return announcements.filtered(lambda ann: not ann.group_ids or bool(user_groups & ann.group_ids))

    def _prepare_backend_message_payload(self):
        """Return plain message text plus clickable links for the backend home screen.

        Users can paste normal URLs in the message. This helper extracts those
        URLs and the frontend renders them as buttons that open in a new tab.
        If an older record contains a typed HTML anchor, the href is also extracted.
        """
        self.ensure_one()
        raw_message = self.message or ""

        href_urls = re.findall(r"href=[\"']([^\"']+)[\"']", raw_message, flags=re.IGNORECASE)
        plain_message = html2plaintext(raw_message) if "<" in raw_message and ">" in raw_message else raw_message

        url_pattern = r"https?://[^\s<>\"']+"
        text_urls = re.findall(url_pattern, plain_message)

        urls = []
        for url in href_urls + text_urls:
            clean_url = url.strip().rstrip(".,;)]")
            if clean_url and clean_url not in urls:
                urls.append(clean_url)

        clean_message = re.sub(url_pattern, "", plain_message).strip()

        return {
            "message": clean_message,
            "links": [
                {"url": url, "label": "Open Link" if len(urls) == 1 else "Open Link %s" % (idx + 1)}
                for idx, url in enumerate(urls)
            ],
        }

    @api.model
    def get_backend_announcements(self):
        """Payload used by the backend home screen announcement cards."""
        color_to_type = {
            "primary": "info",
            "success": "success",
            "warning": "warning",
            "danger": "danger",
        }
        result = []
        for ann in self._get_visible_announcements_for_current_user(target="backend", limit=5):
            payload = ann._prepare_backend_message_payload()
            result.append({
                "id": ann.id,
                "title": ann.name,
                "message": payload["message"],
                "links": payload["links"],
                "type": color_to_type.get(ann.color, "info"),
            })
        return result
