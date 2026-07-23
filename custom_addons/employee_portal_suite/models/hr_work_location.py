from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import math


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    # Kept only for backward compatibility with existing databases. New setup
    # must use project_line_ids so one work location can contain many projects.
    project_id = fields.Many2one(
        "project.project",
        string="Legacy Project",
        ondelete="restrict",
        help="Legacy single-project link. Use Work Location Projects instead.",
    )

    project_line_ids = fields.One2many(
        "hr.work.location.project",
        "work_location_id",
        string="Projects",
        copy=True,
    )
    project_ids = fields.Many2many(
        "project.project",
        string="Available Projects",
        compute="_compute_project_ids",
    )

    # Legacy work-location geofence fields are retained so existing records do
    # not break. New geolocation is configured per project line.
    geo_latitude = fields.Float(string="Legacy Latitude", digits=(10, 7))
    geo_longitude = fields.Float(string="Legacy Longitude", digits=(10, 7))
    geo_radius = fields.Integer(string="Legacy Allowed Radius (meters)", default=200)
    geo_enforce = fields.Boolean(string="Legacy Enforce Geofencing", default=False)

    @api.depends("project_line_ids.project_id", "project_id")
    def _compute_project_ids(self):
        for location in self:
            projects = location.project_line_ids.mapped("project_id")
            if not projects and location.project_id:
                projects = location.project_id
            location.project_ids = projects

    def _get_material_request_projects(self):
        self.ensure_one()
        projects = self.project_line_ids.mapped("project_id")
        if not projects and self.project_id:
            projects = self.project_id
        return projects

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        radius = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        value = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    def _get_enforced_project_locations(self):
        self.ensure_one()
        return self.project_line_ids.filtered(
            lambda line: line.geo_enforce and line.geo_radius > 0
            and (line.geo_latitude or line.geo_longitude)
        )

    def has_project_geofencing(self):
        self.ensure_one()
        return bool(self._get_enforced_project_locations()) or bool(
            self.geo_enforce and self.geo_radius and (self.geo_latitude or self.geo_longitude)
        )

    def check_employee_in_any_project_range(self, employee_lat, employee_lon):
        """Return (allowed, closest_distance, allowed_radius).

        An employee assigned to a work location containing several projects may
        check in from any configured project geofence.
        """
        self.ensure_one()
        lines = self._get_enforced_project_locations()
        if lines:
            checks = []
            for line in lines:
                distance = self._haversine_distance(
                    line.geo_latitude,
                    line.geo_longitude,
                    employee_lat,
                    employee_lon,
                )
                checks.append((distance <= line.geo_radius, distance, line.geo_radius))
            valid = [check for check in checks if check[0]]
            selected = min(valid or checks, key=lambda check: check[1])
            return selected[0], round(selected[1]), selected[2]

        if self.geo_enforce and self.geo_radius and (self.geo_latitude or self.geo_longitude):
            distance = self._haversine_distance(
                self.geo_latitude,
                self.geo_longitude,
                employee_lat,
                employee_lon,
            )
            return distance <= self.geo_radius, round(distance), self.geo_radius

        return True, None, None

    def check_employee_in_range(self, employee_lat, employee_lon):
        """Backward-compatible two-value helper."""
        allowed, distance, _radius = self.check_employee_in_any_project_range(
            employee_lat, employee_lon
        )
        return allowed, distance


class HrWorkLocationProject(models.Model):
    _name = "hr.work.location.project"
    _description = "Work Location Project"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    work_location_id = fields.Many2one(
        "hr.work.location",
        string="Work Location",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="work_location_id.company_id",
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        ondelete="restrict",
        domain="[('company_id', 'in', [False, company_id])]",
    )
    geo_enforce = fields.Boolean(string="Enforce Geofencing", default=False)
    geo_latitude = fields.Float(string="Latitude", digits=(10, 7))
    geo_longitude = fields.Float(string="Longitude", digits=(10, 7))
    geo_radius = fields.Integer(string="Allowed Radius (meters)", default=200)

    _sql_constraints = [
        (
            "work_location_project_unique",
            "unique(work_location_id, project_id)",
            "The same project cannot be added twice to one work location.",
        )
    ]

    @api.constrains("geo_enforce", "geo_latitude", "geo_longitude", "geo_radius")
    def _check_geofence_values(self):
        for line in self:
            if line.geo_enforce:
                if line.geo_radius <= 0:
                    raise ValidationError(_("The geofence radius must be greater than zero."))
                if not line.geo_latitude and not line.geo_longitude:
                    raise ValidationError(_("Set latitude and longitude when geofencing is enabled."))
