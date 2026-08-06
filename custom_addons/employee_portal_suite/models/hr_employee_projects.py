from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Multiple operational work locations. The standard work_location_id is
    # retained as the primary/compatibility location for standard Odoo HR.
    work_location_ids = fields.Many2many(
        "hr.work.location",
        "hr_employee_multi_work_location_rel",
        "employee_id",
        "work_location_id",
        string="Work Locations",
        help=(
            "All work locations available to this employee. Projects configured "
            "inside these locations are used for Material Requests and attendance geofencing."
        ),
    )

    # Retained only so databases upgraded from earlier releases keep loading.
    material_project_ids = fields.Many2many(
        "project.project",
        "hr_employee_material_project_rel",
        "employee_id",
        "project_id",
        string="Deprecated Assigned Projects",
    )

    def _get_effective_work_locations(self):
        """Return selected locations, falling back to Odoo's legacy primary one."""
        self.ensure_one()
        return self.work_location_ids or self.work_location_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            commands = vals.get("work_location_ids")
            if commands and not vals.get("work_location_id"):
                ids = self._extract_m2m_ids(commands)
                if ids:
                    vals["work_location_id"] = ids[0]
        return super().create(vals_list)

    def write(self, vals):
        result = super().write(vals)
        if "work_location_ids" in vals and not self.env.context.get("skip_primary_location_sync"):
            for employee in self:
                primary = employee.work_location_ids[:1]
                if employee.work_location_id != primary:
                    super(HrEmployee, employee.with_context(skip_primary_location_sync=True)).write({
                        "work_location_id": primary.id if primary else False,
                    })
        return result

    @staticmethod
    def _extract_m2m_ids(commands):
        ids = []
        if isinstance(commands, (list, tuple)):
            for command in commands:
                if isinstance(command, int):
                    ids.append(command)
                elif isinstance(command, (list, tuple)) and command:
                    if command[0] == 6:
                        ids = list(command[2] or [])
                    elif command[0] == 4:
                        ids.append(command[1])
        return ids

    def _get_material_request_projects(self):
        self.ensure_one()
        return self._get_effective_work_locations().mapped("project_line_ids.project_id")

    def _find_project_location(self, project):
        self.ensure_one()
        if not project:
            return self.env["hr.work.location"]
        line = self._get_effective_work_locations().mapped("project_line_ids").filtered(
            lambda item: item.project_id == project
        )[:1]
        return line.work_location_id if line else self.env["hr.work.location"]

    def has_project_geofencing(self):
        self.ensure_one()
        locations = self._get_effective_work_locations().sudo()
        return any(location.has_project_geofencing() for location in locations)

    def find_matching_project_geofence(self, employee_lat, employee_lon):
        """Find the nearest valid project geofence across all employee locations."""
        self.ensure_one()
        locations = self._get_effective_work_locations().sudo()
        if not locations:
            return {
                "allowed": True, "distance": None, "radius": None,
                "project_line": self.env["hr.work.location.project"],
                "project": self.env["project.project"],
                "work_location": self.env["hr.work.location"],
            }

        checks = []
        for location in locations:
            lines = location._get_enforced_project_locations()
            for line in lines:
                distance = location._haversine_distance(
                    line.geo_latitude, line.geo_longitude, employee_lat, employee_lon
                )
                checks.append({
                    "allowed": distance <= line.geo_radius,
                    "distance": round(distance),
                    "radius": line.geo_radius,
                    "project_line": line,
                    "project": line.project_id,
                    "work_location": location,
                })

        # Backward compatibility for locations still using the legacy geofence.
        if not checks:
            for location in locations.filtered(
                lambda loc: loc.geo_enforce and loc.geo_radius and (loc.geo_latitude or loc.geo_longitude)
            ):
                distance = location._haversine_distance(
                    location.geo_latitude, location.geo_longitude, employee_lat, employee_lon
                )
                checks.append({
                    "allowed": distance <= location.geo_radius,
                    "distance": round(distance),
                    "radius": location.geo_radius,
                    "project_line": self.env["hr.work.location.project"],
                    "project": location.project_id,
                    "work_location": location,
                })

        if not checks:
            return {
                "allowed": True, "distance": None, "radius": None,
                "project_line": self.env["hr.work.location.project"],
                "project": self.env["project.project"],
                "work_location": self.env["hr.work.location"],
            }

        valid = [check for check in checks if check["allowed"]]
        return min(valid or checks, key=lambda check: check["distance"])

    def check_employee_in_any_project_range(self, employee_lat, employee_lon):
        self.ensure_one()
        match = self.find_matching_project_geofence(employee_lat, employee_lon)
        return match["allowed"], match["distance"], match["radius"]
