# -*- coding: utf-8 -*-
"""Migrate legacy single-project work locations to project rows.

The previous module stored one project and one geofence directly on
hr.work.location.  The new structure stores one row per project.  During the
upgrade, preserve the old assignment and its GPS settings as the first row.
The INSERT is deliberately idempotent and does not alter rows already created
manually in the new table.
"""


def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO hr_work_location_project (
            sequence,
            work_location_id,
            project_id,
            geo_enforce,
            geo_latitude,
            geo_longitude,
            geo_radius,
            create_uid,
            create_date,
            write_uid,
            write_date
        )
        SELECT
            10,
            location.id,
            location.project_id,
            COALESCE(location.geo_enforce, FALSE),
            COALESCE(location.geo_latitude, 0.0),
            COALESCE(location.geo_longitude, 0.0),
            COALESCE(location.geo_radius, 200),
            1,
            NOW(),
            1,
            NOW()
        FROM hr_work_location AS location
        WHERE location.project_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM hr_work_location_project AS project_line
              WHERE project_line.work_location_id = location.id
                AND project_line.project_id = location.project_id
          )
        """
    )
