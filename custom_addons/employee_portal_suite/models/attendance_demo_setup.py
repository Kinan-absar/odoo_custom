"""Explicit, administrator-triggered sample data for attendance recordings."""
from datetime import datetime, time, timedelta
import math
import secrets

import pytz

from odoo import fields, models, _
from odoo.exceptions import AccessError, UserError


def demo_sessions(today, timezone, latitude, longitude, radius):
    """Ten closed, non-overlapping historical sessions; never an open check-in."""
    tz = pytz.timezone(timezone)
    days = []
    day = today - timedelta(days=1)
    while len(days) < 10:
        if day.weekday() < 5:
            days.append(day)
        day -= timedelta(days=1)
    rows = []
    for index, day in enumerate(days):
        start = tz.localize(datetime.combine(day, time(8)), is_dst=None)
        end = tz.localize(datetime.combine(day, time(16)), is_dst=None)
        check_in = start.astimezone(pytz.utc).replace(tzinfo=None)
        check_out = end.astimezone(pytz.utc).replace(tzinfo=None)
        outside = index in (1, 5)
        offline = index in (0, 3, 6)
        # Move north (or south near the pole) by at least 500 m and > radius.
        offset = max(radius * 2, 500) / 111195.0
        out_lat = latitude + offset if latitude + offset < 90 else latitude - offset
        distance = 6371000 * abs(math.radians(out_lat - latitude)) if outside else 0.0
        rows.append({
            'check_in': check_in,
            'check_out': check_out,
            'in_mode': 'portal',
            'out_mode': 'portal',
            'check_in_geo_latitude': latitude,
            'check_in_geo_longitude': longitude,
            'check_out_geo_latitude': out_lat if outside else latitude,
            'check_out_geo_longitude': longitude,
            'check_in_project_distance': 0.0,
            'check_out_project_distance': distance,
            'checkout_outside_location': outside,
            'attendance_exception_state': 'pending' if index == 1 else 'resolved',
            'check_in_recorded_offline': offline,
            'check_out_recorded_offline': offline,
            'offline_check_in_synced_at': check_out + timedelta(minutes=15) if offline else False,
            'offline_check_out_synced_at': check_out + timedelta(minutes=15) if offline else False,
            'eps_demo_scenario': ('Outside site — pending review' if index == 1 else
                                  'Outside site — resolved' if outside else
                                  'Offline check-in/out — synced' if offline else
                                  'Normal portal attendance'),
        })
    return rows


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    eps_demo_scenario = fields.Char(string='Demo Scenario', readonly=True, copy=False, index=True)


class AttendanceDemoSetup(models.TransientModel):
    _name = 'employee.portal.attendance.demo.setup'
    _description = 'Attendance Demo Setup'

    name = fields.Char(string='Demo Employee', required=True, default='Alex Morgan (Attendance Demo)')
    login = fields.Char(required=True, default=lambda self: 'attendance.demo.%s@example.invalid' % secrets.token_hex(3))
    demo_password = fields.Char(string='Demo Password', required=True, copy=False,
                                default=lambda self: secrets.token_urlsafe(18))
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    timezone = fields.Selection(selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
                                required=True, default=lambda self: self.env.user.tz or 'UTC')
    latitude = fields.Float(required=True, digits=(10, 7), default=52.2433030)
    longitude = fields.Float(required=True, digits=(10, 7), default=11.0029700)
    radius = fields.Integer(string='Allowed Radius (metres)', required=True, default=200)
    employee_id = fields.Many2one('hr.employee', readonly=True)
    project_id = fields.Many2one('project.project', readonly=True)
    location_id = fields.Many2one('hr.work.location', readonly=True)

    def _check_admin(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(_('Only a Settings administrator can create attendance demo data.'))

    def action_create_demo(self):
        self.ensure_one()
        self._check_admin()
        if self.employee_id:
            return self._reopen()
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select a company enabled in your current session.'))
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise UserError(_('Enter valid latitude and longitude.'))
        if self.radius <= 0 or (not self.latitude and not self.longitude):
            raise UserError(_('Enter a positive radius and a non-zero site location.'))
        login = (self.login or '').strip()
        if not login or len(self.demo_password or '') < 12:
            raise UserError(_('Enter a login and a password of at least 12 characters.'))
        if self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', login)]):
            raise UserError(_('This login already exists. Choose a new demo login; existing users are never changed.'))

        # No invitation/reset emails; credentials are shown only in this admin wizard.
        env = self.env(context=dict(self.env.context, tracking_disable=True,
                                   mail_create_nosubscribe=True, mail_create_nolog=True,
                                   no_reset_password=True))
        groups = [env.ref(xmlid).id for xmlid in (
            'base.group_portal',
            'employee_portal_suite.group_employee_portal',
            'employee_portal_suite.group_employee_portal_employee',
            'employee_portal_suite.group_portal_attendance_user',
        )]
        user = env['res.users'].sudo().create({
            'name': self.name, 'login': login, 'password': self.demo_password,
            'email': False, 'tz': self.timezone,
            'company_id': self.company_id.id, 'company_ids': [(6, 0, [self.company_id.id])],
            'groups_id': [(6, 0, groups)],
        })
        project = env['project.project'].sudo().create({
            'name': 'Demo — Riverside Project', 'company_id': self.company_id.id,
        })
        location = env['hr.work.location'].sudo().create({
            'name': 'Demo — Riverside Site', 'company_id': self.company_id.id,
            'address_id': self.company_id.partner_id.id,
        })
        site = env['hr.work.location.project'].sudo().create({
            'work_location_id': location.id, 'project_id': project.id,
            'geo_enforce': True, 'geo_latitude': self.latitude,
            'geo_longitude': self.longitude, 'geo_radius': self.radius,
        })
        employee = env['hr.employee'].sudo().create({
            'name': self.name, 'job_title': 'Site Engineer (Demo)',
            'company_id': self.company_id.id, 'user_id': user.id,
            'work_location_id': location.id, 'work_location_ids': [(6, 0, [location.id])],
            'tz': self.timezone,
        })
        today = datetime.now(pytz.timezone(self.timezone)).date()
        rows = demo_sessions(today, self.timezone, self.latitude, self.longitude, self.radius)
        for row in rows:
            row.update({
                'employee_id': employee.id,
                'check_in_project_id': project.id, 'check_out_project_id': project.id,
                'check_in_work_location_id': location.id, 'check_out_work_location_id': location.id,
                'check_in_project_location_id': site.id, 'check_out_project_location_id': site.id,
            })
            if row['check_in_recorded_offline']:
                row['offline_check_in_event_id'] = 'demo-in-' + secrets.token_hex(16)
                row['offline_check_out_event_id'] = 'demo-out-' + secrets.token_hex(16)
        env['hr.attendance'].sudo().create(rows)
        # Do not seed a fictitious trusted token: the real first browser registers
        # through register_or_check(), retaining the existing device security flow.
        self.write({'employee_id': employee.id, 'project_id': project.id, 'location_id': location.id,
                    'login': login})
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def action_view_attendance(self):
        self.ensure_one()
        self._check_admin()
        if not self.employee_id:
            raise UserError(_('Create the demo first.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Demo Attendance'),
            'res_model': 'hr.attendance', 'view_mode': 'list,form',
            'views': [(self.env.ref('employee_portal_suite.view_attendance_flag_demo_list').id, 'list'),
                      (self.env.ref('employee_portal_suite.view_hr_attendance_flag_form').id, 'form')],
            'domain': [('employee_id', '=', self.employee_id.id)],
            'context': {'default_employee_id': self.employee_id.id},
        }
