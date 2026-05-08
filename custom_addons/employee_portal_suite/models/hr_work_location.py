from odoo import models, fields, api
import math


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        ondelete="restrict",
        help="Project linked to this work location. Used for approvals and routing.",
    )

    # ------------------------------------------------------------------
    # Geolocation fields
    # ------------------------------------------------------------------
    geo_latitude = fields.Float(
        string="Latitude",
        digits=(10, 7),
        help="GPS latitude of this work location (e.g. 24.7136).",
    )
    geo_longitude = fields.Float(
        string="Longitude",
        digits=(10, 7),
        help="GPS longitude of this work location (e.g. 46.6753).",
    )
    geo_radius = fields.Integer(
        string="Allowed Radius (meters)",
        default=200,
        help=(
            "Maximum distance (in metres) from the location coordinates "
            "within which an employee is allowed to check in. "
            "Set to 0 to disable geofencing for this location."
        ),
    )
    geo_enforce = fields.Boolean(
        string="Enforce Geofencing",
        default=False,
        help=(
            "If enabled, employees must be within the allowed radius to check in "
            "from the portal. Requires latitude and longitude to be set."
        ),
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Return the great-circle distance in metres between two GPS points."""
        R = 6_371_000  # Earth radius in metres
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def check_employee_in_range(self, employee_lat, employee_lon):
        """Return (ok: bool, distance_m: float | None).

        ok is True when geofencing is disabled, coordinates are not set,
        or the employee is within the allowed radius.
        """
        self.ensure_one()
        if not self.geo_enforce or not self.geo_radius:
            return True, None
        if not self.geo_latitude and not self.geo_longitude:
            return True, None
        distance = self._haversine_distance(
            self.geo_latitude, self.geo_longitude, employee_lat, employee_lon
        )
        return distance <= self.geo_radius, round(distance)
