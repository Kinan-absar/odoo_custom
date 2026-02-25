from odoo import models, fields
from odoo.tools import date_utils
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

    group_ids = fields.Many2many(
        "res.groups",
        string="Visible To Groups",
        help="If empty, visible to all portal users"
    )

    color = fields.Selection([
        ('primary', 'Blue'),
        ('success', 'Green'),
        ('warning', 'Yellow'),
        ('danger', 'Red'),
    ], default='primary')
