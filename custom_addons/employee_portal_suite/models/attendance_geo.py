from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.http import request
from datetime import timedelta
import math


class AttendanceGeo(models.Model):
    _name = 'attendance.geo'
    _description = 'Employee Geolocation Attendance'
    _order = 'check_in_time desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ---------------------------------------------------------
    # FIELDS
    # ---------------------------------------------------------
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )

    work_location_id = fields.Many2one(
        'hr.work.location',
        string='Work Location',
        required=True,
        tracking=True,
        help="The work location assigned to the employee at check-in."
    )

    check_in_lat = fields.Float(string="Check-in Latitude", digits=(10, 6))
    check_in_lng = fields.Float(string="Check-in Longitude", digits=(10, 6))
    check_in_time = fields.Datetime(string="Check-in Time", tracking=True)

    check_out_lat = fields.Float(string="Check-out Latitude", digits=(10, 6))
    check_out_lng = fields.Float(string="Check-out Longitude", digits=(10, 6))
    check_out_time = fields.Datetime(string="Check-out Time", tracking=True)

    state = fields.Selection([
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
    ], default='checked_in', tracking=True)

    distance_meters = fields.Float(string="Distance (m)", readonly=True)

    device_info = fields.Char(string="Device Info")
    ip_address = fields.Char(string="IP Address")

    # ---------------------------------------------------------
    # UTIL
    # ---------------------------------------------------------
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Return distance in meters between two GPS points."""
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    # ---------------------------------------------------------
    # CHECK-IN
    # ---------------------------------------------------------
    @api.model
    def create_geo_checkin(self, employee_id, lat, lng, allowed_lat, allowed_lng, max_distance_m=200):
        """Create a check-in record with location validation."""
        distance = self._haversine_distance(lat, lng, allowed_lat, allowed_lng)

        if distance > max_distance_m:
            raise UserError(_("Check-in rejected. Out of allowed area. (%.2f m)") % distance)

        employee = self.env['hr.employee'].sudo().browse(employee_id)
        work_loc = employee.work_location_id

        rec = self.create({
            'employee_id': employee.id,
            'work_location_id': work_loc.id,
            'check_in_lat': lat,
            'check_in_lng': lng,
            'check_in_time': fields.Datetime.now(),
            'distance_meters': distance,
            'state': 'checked_in',
        })

        rec.message_post(body=_("Employee checked in (%.2f m from allowed point).") % distance)

        return rec

    # ---------------------------------------------------------
    # CHECK-OUT
    # ---------------------------------------------------------
    def action_checkout(self, lat, lng):
        """Record check-out with updated location."""
        self.ensure_one()

        work_lat = self.work_location_id.latitude
        work_lng = self.work_location_id.longitude

        distance = self._haversine_distance(lat, lng, work_lat, work_lng)

        self.write({
            'check_out_lat': lat,
            'check_out_lng': lng,
            'check_out_time': fields.Datetime.now(),
            'state': 'checked_out',
        })

        self.message_post(body=_("Employee checked out (%.2f m from allowed point).") % distance)

    # ---------------------------------------------------------
    # CRON: AUTO CHECKOUT
    # ---------------------------------------------------------
    @api.model
    def _cron_auto_checkout(self):
        max_hours = 12
        cutoff = fields.Datetime.now() - timedelta(hours=max_hours)

        records = self.search([
            ('state', '=', 'checked_in'),
            ('check_in_time', '<=', cutoff),
        ])

        for rec in records:
            rec.write({
                'check_out_time': fields.Datetime.now(),
                'state': 'checked_out',
            })
            rec.message_post(
                body=_("⚠ Auto-checkout executed by system after %s hours.") % max_hours
            )
