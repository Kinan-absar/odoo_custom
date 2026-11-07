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

    def _get_material_request_projects(self, employee=None):
        """Projects available at this Work Location.

        Projects are shared by every employee assigned to this Work Location.
        """
        self.ensure_one()
        lines = self.project_line_ids
        projects = lines.mapped("project_id")
        if not projects and not employee and self.project_id:
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

    def _get_enforced_project_locations(self, employee=None):
        self.ensure_one()
        lines = self.project_line_ids.filtered(
            lambda line: line.geo_enforce and line.geo_radius > 0
            and (line.geo_latitude or line.geo_longitude)
        )
        return lines

    def has_project_geofencing(self, employee=None):
        self.ensure_one()
        return bool(self._get_enforced_project_locations(employee=employee)) or bool(
            self.geo_enforce and self.geo_radius and (self.geo_latitude or self.geo_longitude)
        )

    def find_matching_project_geofence(self, employee_lat, employee_lon, employee=None):
        """Return details for the nearest applicable geofence.

        The returned dictionary contains ``allowed``, ``distance``, ``radius``
        and, for project geofences, ``project_line`` and ``project``. If more
        than one project radius contains the employee, the nearest project is
        selected. This method is the single source of truth used by attendance
        check-in/check-out so the exact matched project can be stored.
        """
        self.ensure_one()
        lines = self._get_enforced_project_locations(employee=employee)
        if lines:
            checks = []
            for line in lines:
                distance = self._haversine_distance(
                    line.geo_latitude,
                    line.geo_longitude,
                    employee_lat,
                    employee_lon,
                )
                checks.append({
                    'allowed': distance <= line.geo_radius,
                    'distance': round(distance),
                    'radius': line.geo_radius,
                    'project_line': line,
                    'project': line.project_id,
                })
            valid = [check for check in checks if check['allowed']]
            return min(valid or checks, key=lambda check: check['distance'])

        if self.geo_enforce and self.geo_radius and (self.geo_latitude or self.geo_longitude):
            distance = self._haversine_distance(
                self.geo_latitude,
                self.geo_longitude,
                employee_lat,
                employee_lon,
            )
            return {
                'allowed': distance <= self.geo_radius,
                'distance': round(distance),
                'radius': self.geo_radius,
                'project_line': self.env['hr.work.location.project'],
                'project': self.project_id,
            }

        return {
            'allowed': True,
            'distance': None,
            'radius': None,
            'project_line': self.env['hr.work.location.project'],
            'project': self.env['project.project'],
        }

    def check_employee_in_any_project_range(self, employee_lat, employee_lon, employee=None):
        """Backward-compatible three-value geofence helper."""
        match = self.find_matching_project_geofence(
            employee_lat, employee_lon, employee=employee
        )
        return match['allowed'], match['distance'], match['radius']

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
