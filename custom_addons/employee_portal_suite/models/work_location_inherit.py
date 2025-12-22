from odoo import models, fields


class WorkLocationGeo(models.Model):
    _inherit = 'hr.work.location'

    latitude = fields.Float(
        string="Latitude",
        digits=(10, 6),
        help="GPS latitude for work location check-in."
    )

    longitude = fields.Float(
        string="Longitude",
        digits=(10, 6),
        help="GPS longitude for work location check-in."
    )

    allowed_radius_meters = fields.Integer(
        string="Allowed Radius (m)",
        default=200,
        help="Maximum allowed distance for employee check-in."
    )
