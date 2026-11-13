from odoo import http, fields
from odoo.http import request
from datetime import datetime, timedelta, timezone
import pytz
import json
import logging
import secrets

_logger = logging.getLogger(__name__)


def _tz_convert(dt, employee):
    """Convert a naive UTC datetime (as stored by Odoo) to the employee's
    local timezone and return a formatted string like '11:00 AM'."""
    if not dt:
        return ''
    tz_name = (employee and employee.tz) or 'UTC'
    try:
        tz = pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        tz = pytz.utc
    # Odoo stores datetimes as naive UTC — make them timezone-aware then convert
    dt_utc = pytz.utc.localize(dt)
    return dt_utc.astimezone(tz)


def _is_attendance_only():
    """Return True when the current user belongs ONLY to the Attendance Only
    group and should be restricted to /my/employee/attendance."""
    return request.env.user.has_group(
        'employee_portal_suite.group_attendance_only'
    )


def _client_event_time(value):
    """Parse a browser ISO-8601 timestamp and return naive UTC for Odoo."""
    if not value or not isinstance(value, str):
        raise ValueError('missing_timestamp')
    raw = value.strip()
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        raise ValueError('timezone_required')
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _offline_time_allowed(dt):
    now = datetime.utcnow()
    return (now - timedelta(days=7)) <= dt <= (now + timedelta(minutes=5))


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        status=status,
        headers=[
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Cache-Control', 'no-store'),
        ],
    )



def _trusted_device(employee, token, touch=True):
    return request.env['employee.portal.attendance.device'].sudo().validate_token(
        employee, token, touch=touch
    )


class EmployeePortalAttendance(http.Controller):

    # ---------------------------------------------------------
    # ATTENDANCE PAGE
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance', type='http', auth='user', website=True)
    def portal_attendance(self, **kw):
        user = request.env.user

        if not user.share:
            return request.redirect('/web')
        if not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return request.redirect('/my/employee')

        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        # Current open attendance (checked in, not yet checked out)
        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        # Last 10 attendance records
        recent_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
        ], order='check_in desc', limit=10)

        # Today's total worked hours
        tz = pytz.timezone(employee.tz or 'UTC')
        now_local = datetime.now(tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_local.astimezone(pytz.utc).replace(tzinfo=None)

        today_attendances = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(today_start_utc)),
        ])

        today_hours = sum(a.worked_hours for a in today_attendances)

        # Success/error message from redirect
        success_message = kw.get('success')
        error_message = kw.get('error')

        # Trusted attendance device bootstrap. Keep online attendance independent
        # from JavaScript: the server issues a persistent device token cookie and
        # registers/checks it when the Attendance page opens.
        device_cookie_name = 'eps_attendance_device_v1'
        device_token = (request.httprequest.cookies.get(device_cookie_name) or '').strip()
        if len(device_token) < 32 or len(device_token) > 512:
            device_token = secrets.token_hex(32)
        device_label = request.httprequest.headers.get('Sec-CH-UA-Platform') or 'Attendance Device'
        user_agent = request.httprequest.headers.get('User-Agent', '')
        device_result = request.env['employee.portal.attendance.device'].sudo().register_or_check(
            employee, user, device_token, device_label=device_label, user_agent=user_agent,
        )
        trusted_device_state = device_result.get('state') or 'unknown'
        if error_message == 'device_not_trusted' and trusted_device_state == 'trusted':
            error_message = False

        response = request.render('employee_portal_suite.employee_portal_attendance', {
            'employee': employee,
            'open_attendance': open_attendance,
            'recent_attendances': recent_attendances,
            'today_hours': today_hours,
            'is_checked_in': bool(open_attendance),
            'success_message': success_message,
            'error_message': error_message,
            'page_name': 'attendance',
            'geo_enforce': employee.sudo().has_project_geofencing(),
            'server_check_in_iso': (
                pytz.utc.localize(open_attendance.check_in).isoformat().replace('+00:00', 'Z')
                if open_attendance and open_attendance.check_in else ''
            ),
            # Pass a callable so the XML template can convert UTC → local time.
            # Usage in QWeb: t-esc="fmt_dt(att.check_in, '%I:%M %p')"
            'fmt_dt': lambda dt, fmt='%I:%M %p': (
                _tz_convert(dt, employee).strftime(fmt) if dt else ''
            ),
            'trusted_device_token': device_token,
            'trusted_device_state': trusted_device_state,
        })
        response.set_cookie(
            device_cookie_name, device_token, max_age=31536000, path='/',
            secure=True, httponly=False, samesite='Lax',
        )
        return response

    # ---------------------------------------------------------
    # CHECK-IN
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance/check_in', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_attendance_check_in(self, **post):
        user = request.env.user

        if not user.share:
            return request.redirect('/web')
        if not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return request.redirect('/my/employee')

        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        if not _trusted_device(employee, post.get('trusted_device_token')):
            return request.redirect('/my/employee/attendance?error=device_not_trusted')

        # Prevent double check-in
        existing = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if existing:
            return request.redirect('/my/employee/attendance?error=already_checked_in')

        # ------------------------------------------------------------------
        # Geolocation validation and exact project detection
        # ------------------------------------------------------------------
        attendance_vals = {
            'employee_id': employee.id,
            'check_in': fields.Datetime.now(),
        }
        if employee.sudo().has_project_geofencing():
            try:
                emp_lat = float(post.get('geo_lat', ''))
                emp_lon = float(post.get('geo_lon', ''))
            except (TypeError, ValueError):
                # Browser did not send coordinates — reject if enforcement is on
                return request.redirect('/my/employee/attendance?error=geo_required')

            match = employee.sudo().find_matching_project_geofence(emp_lat, emp_lon)
            if not match['allowed']:
                return request.redirect(
                    '/my/employee/attendance?error=geo_out_of_range&distance=%d&radius=%d'
                    % (match['distance'] or 0, match['radius'] or 0)
                )

            attendance_vals.update({
                'check_in_geo_latitude': emp_lat,
                'check_in_geo_longitude': emp_lon,
                'check_in_project_distance': match['distance'] or 0.0,
                'check_in_project_id': match['project'].id if match['project'] else False,
                'check_in_project_location_id': (
                    match['project_line'].id if match['project_line'] else False
                ),
                'check_in_work_location_id': (
                    match['work_location'].id if match.get('work_location') else False
                ),
                # Populate Odoo's native GPS fields too, so the standard
                # Attendance form no longer shows an empty Location section.
                'in_latitude': emp_lat,
                'in_longitude': emp_lon,
                'in_mode': 'portal',
            })

        try:
            request.env['hr.attendance'].sudo().create(attendance_vals)
            return request.redirect('/my/employee/attendance?success=checked_in')
        except Exception:
            return request.redirect('/my/employee/attendance?error=check_in_failed')

    # ---------------------------------------------------------
    # CHECK-OUT
    # ---------------------------------------------------------
    @http.route('/my/employee/attendance/check_out', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_attendance_check_out(self, **post):
        user = request.env.user

        if not user.share:
            return request.redirect('/web')
        if not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return request.redirect('/my/employee')

        employee = user.employee_id

        if not employee:
            return request.redirect('/my/employee')

        if not _trusted_device(employee, post.get('trusted_device_token')):
            return request.redirect('/my/employee/attendance?error=device_not_trusted')

        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ], limit=1)

        if not open_attendance:
            return request.redirect('/my/employee/attendance?error=not_checked_in')

        # ------------------------------------------------------------------
        # Geolocation check on check-out (non-blocking: always allow,
        # but flag the record when the employee is outside the allowed zone)
        # ------------------------------------------------------------------
        outside_location = False
        checkout_match = None
        emp_lat = emp_lon = None
        if employee.sudo().has_project_geofencing():
            try:
                emp_lat = float(post.get('geo_lat', ''))
                emp_lon = float(post.get('geo_lon', ''))
                checkout_match = employee.sudo().find_matching_project_geofence(emp_lat, emp_lon)
                if not checkout_match['allowed']:
                    outside_location = True
            except (TypeError, ValueError):
                # Coordinates not provided or invalid — flag conservatively
                outside_location = True

        try:
            vals = {'check_out': fields.Datetime.now()}
            if emp_lat is not None and emp_lon is not None:
                vals.update({
                    'check_out_geo_latitude': emp_lat,
                    'check_out_geo_longitude': emp_lon,
                    'out_latitude': emp_lat,
                    'out_longitude': emp_lon,
                    'out_mode': 'portal',
                })
            if checkout_match:
                vals.update({
                    'check_out_project_distance': checkout_match['distance'] or 0.0,
                    'check_out_project_id': (
                        checkout_match['project'].id
                        if checkout_match['allowed'] and checkout_match['project']
                        else False
                    ),
                    'check_out_project_location_id': (
                        checkout_match['project_line'].id
                        if checkout_match['allowed'] and checkout_match['project_line']
                        else False
                    ),
                    'check_out_work_location_id': (
                        checkout_match['work_location'].id
                        if checkout_match['allowed'] and checkout_match.get('work_location')
                        else False
                    ),
                })
            if outside_location:
                vals['checkout_outside_location'] = True
            open_attendance.sudo().with_context(from_portal_checkout=True).write(vals)
            if outside_location:
                return request.redirect('/my/employee/attendance?success=checked_out&warn=outside_location')
            return request.redirect('/my/employee/attendance?success=checked_out')
        except Exception as e:
            return request.redirect('/my/employee/attendance?error=check_out_failed')

    # ---------------------------------------------------------
    # TRUSTED ATTENDANCE DEVICE
    # ---------------------------------------------------------
    @http.route(
        '/my/employee/attendance/device/status',
        type='http', auth='user', methods=['POST'], csrf=False,
    )
    def portal_attendance_device_status(self, **kwargs):
        user = request.env.user
        if not user.share or not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return _json_response({'error': 'forbidden'}, 403)
        employee = user.employee_id
        if not employee:
            return _json_response({'error': 'employee_required'}, 403)
        try:
            payload = request.httprequest.get_json(silent=True) or {}
        except Exception:
            return _json_response({'error': 'invalid_json'}, 400)
        token = str(payload.get('token') or '').strip()
        label = str(payload.get('device_label') or '').strip()[:128]
        user_agent = request.httprequest.headers.get('User-Agent', '')
        result = request.env['employee.portal.attendance.device'].sudo().register_or_check(
            employee, user, token, device_label=label, user_agent=user_agent,
        )
        state = result.get('state')
        response = _json_response({
            'state': state,
            'trusted': state == 'trusted',
            'pending': state == 'pending',
            'auto_trusted': bool(result.get('auto_trusted')),
        })
        if token:
            response.set_cookie(
                'eps_attendance_device_v1', token, max_age=31536000, path='/',
                secure=True, httponly=False, samesite='Lax',
            )
        return response

    # ---------------------------------------------------------
    # EXPLICIT DEVICE CHANGE REQUEST (no registration on page visit)
    # ---------------------------------------------------------
    @http.route(
        '/my/employee/attendance/device/request_change',
        type='http', auth='user', website=True, methods=['POST'], csrf=True,
    )
    def portal_attendance_device_request_change(self, **post):
        user = request.env.user
        if not user.share or not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return request.redirect('/my/employee')
        employee = user.employee_id
        if not employee:
            return request.redirect('/my/employee')

        # Only the browser that possesses the attendance device cookie can
        # request registration for that device. Never trust a posted token.
        token = (request.httprequest.cookies.get('eps_attendance_device_v1') or '').strip()
        if len(token) < 32 or len(token) > 512:
            return request.redirect('/my/employee/attendance?error=device_cookie_missing')
        label = request.httprequest.headers.get('Sec-CH-UA-Platform') or 'Attendance Device'
        user_agent = request.httprequest.headers.get('User-Agent', '')
        result = request.env['employee.portal.attendance.device'].sudo().register_or_check(
            employee, user, token, device_label=label, user_agent=user_agent,
            request_change=True,
        )
        state = result.get('state')
        if state == 'pending':
            return request.redirect('/my/employee/attendance?success=device_request_submitted')
        if state == 'trusted':
            return request.redirect('/my/employee/attendance?success=device_already_trusted')
        return request.redirect('/my/employee/attendance?error=device_request_failed')

    # ---------------------------------------------------------
    # OFFLINE PWA SYNC
    # ---------------------------------------------------------
    @http.route(
        '/my/employee/attendance/offline_sync',
        type='http', auth='user', methods=['POST'], csrf=False,
    )
    def portal_attendance_offline_sync(self, **kwargs):
        user = request.env.user
        if not user.share or not user.has_group('employee_portal_suite.group_portal_attendance_user'):
            return _json_response({'error': 'forbidden'}, 403)
        employee = user.employee_id
        if not employee:
            return _json_response({'error': 'employee_required'}, 403)

        try:
            payload = request.httprequest.get_json(silent=True) or {}
        except Exception:
            return _json_response({'error': 'invalid_json'}, 400)
        events = payload.get('events') or []
        if not isinstance(events, list) or len(events) > 100:
            return _json_response({'error': 'invalid_events'}, 400)

        # The client sends events in the order they happened. Preserve that order;
        # this lets an offline check-in followed by an offline check-out create one
        # normal attendance record on reconnect.
        results = []
        for raw in events:
            event_id = str((raw or {}).get('id') or '').strip()[:128]
            kind = (raw or {}).get('kind')
            result = {'id': event_id, 'status': 'failed'}
            if not event_id or kind not in ('check_in', 'check_out'):
                result.update(code='invalid_event', message='Invalid offline attendance event.')
                results.append(result)
                continue

            device_token = str((raw or {}).get('device_token') or '').strip()
            if not _trusted_device(employee, device_token):
                result.update(code='device_not_trusted', message='This phone is not the trusted attendance device for this employee.')
                results.append(result)
                continue

            try:
                captured_at = _client_event_time(raw.get('captured_at'))
            except Exception:
                result.update(code='invalid_time', message='The saved device time is invalid.')
                results.append(result)
                continue
            if not _offline_time_allowed(captured_at):
                result.update(code='time_out_of_range', message='The saved attendance time is too old or in the future.')
                results.append(result)
                continue

            lat = lon = None
            try:
                if raw.get('lat') is not None and raw.get('lon') is not None:
                    lat = float(raw.get('lat'))
                    lon = float(raw.get('lon'))
            except (TypeError, ValueError):
                lat = lon = None

            Attendance = request.env['hr.attendance'].sudo()
            # Idempotency: a reconnect/retry must never create a second record.
            duplicate_domain = [
                ('employee_id', '=', employee.id),
                ('offline_check_in_event_id' if kind == 'check_in' else 'offline_check_out_event_id', '=', event_id),
            ]
            duplicate = Attendance.search(duplicate_domain, limit=1)
            if duplicate:
                result['status'] = 'duplicate'
                results.append(result)
                continue

            try:
                if kind == 'check_in':
                    existing = Attendance.search([
                        ('employee_id', '=', employee.id),
                        ('check_out', '=', False),
                    ], limit=1)
                    if existing:
                        result.update(code='already_checked_in', message='You are already checked in on the server.')
                        results.append(result)
                        continue

                    vals = {
                        'employee_id': employee.id,
                        'check_in': captured_at,
                        'in_mode': 'portal',
                        'check_in_recorded_offline': True,
                        'offline_check_in_event_id': event_id,
                        'offline_check_in_synced_at': fields.Datetime.now(),
                    }
                    if employee.sudo().has_project_geofencing():
                        if lat is None or lon is None:
                            result.update(code='geo_required', message='Location was not captured for the offline check-in.')
                            results.append(result)
                            continue
                        match = employee.sudo().find_matching_project_geofence(lat, lon)
                        if not match['allowed']:
                            result.update(code='geo_out_of_range', message='The offline check-in location is outside the allowed work zone.')
                            results.append(result)
                            continue
                        vals.update({
                            'check_in_geo_latitude': lat,
                            'check_in_geo_longitude': lon,
                            'check_in_project_distance': match['distance'] or 0.0,
                            'check_in_project_id': match['project'].id if match['project'] else False,
                            'check_in_project_location_id': match['project_line'].id if match['project_line'] else False,
                            'check_in_work_location_id': match['work_location'].id if match.get('work_location') else False,
                            'in_latitude': lat,
                            'in_longitude': lon,
                        })
                    elif lat is not None and lon is not None:
                        vals.update({'in_latitude': lat, 'in_longitude': lon})
                    Attendance.create(vals)
                    result['status'] = 'synced'

                else:
                    open_attendance = Attendance.search([
                        ('employee_id', '=', employee.id),
                        ('check_out', '=', False),
                    ], order='check_in desc', limit=1)
                    if not open_attendance:
                        result.update(code='not_checked_in', message='No open attendance record exists on the server.')
                        results.append(result)
                        continue
                    if captured_at < open_attendance.check_in:
                        result.update(code='checkout_before_checkin', message='The saved check-out time is before check-in.')
                        results.append(result)
                        continue

                    vals = {
                        'check_out': captured_at,
                        'out_mode': 'portal',
                        'check_out_recorded_offline': True,
                        'offline_check_out_event_id': event_id,
                        'offline_check_out_synced_at': fields.Datetime.now(),
                    }
                    outside_location = False
                    checkout_match = None
                    if employee.sudo().has_project_geofencing():
                        if lat is not None and lon is not None:
                            checkout_match = employee.sudo().find_matching_project_geofence(lat, lon)
                            outside_location = not checkout_match['allowed']
                        else:
                            outside_location = True
                    if lat is not None and lon is not None:
                        vals.update({
                            'check_out_geo_latitude': lat,
                            'check_out_geo_longitude': lon,
                            'out_latitude': lat,
                            'out_longitude': lon,
                        })
                    if checkout_match:
                        vals.update({
                            'check_out_project_distance': checkout_match['distance'] or 0.0,
                            'check_out_project_id': checkout_match['project'].id if checkout_match['allowed'] and checkout_match['project'] else False,
                            'check_out_project_location_id': checkout_match['project_line'].id if checkout_match['allowed'] and checkout_match['project_line'] else False,
                            'check_out_work_location_id': checkout_match['work_location'].id if checkout_match['allowed'] and checkout_match.get('work_location') else False,
                        })
                    if outside_location:
                        vals['checkout_outside_location'] = True
                    open_attendance.with_context(from_portal_checkout=True).write(vals)
                    result['status'] = 'synced'
            except Exception:
                _logger.exception('Failed to sync offline attendance event %s for employee %s', event_id, employee.id)
                result.update(code='server_error', message='The attendance event could not be synchronized.')
            results.append(result)

        open_attendance = request.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id), ('check_out', '=', False),
        ], limit=1)
        open_check_in = ''
        if open_attendance and open_attendance.check_in:
            open_check_in = pytz.utc.localize(open_attendance.check_in).isoformat().replace('+00:00', 'Z')
        return _json_response({
            'results': results,
            'is_checked_in': bool(open_attendance),
            'open_check_in': open_check_in,
        })

