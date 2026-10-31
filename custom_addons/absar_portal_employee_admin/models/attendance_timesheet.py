from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class AttendanceTimesheetService(models.AbstractModel):
    _name = 'absar.attendance.timesheet.service'
    _description = 'Admin Attendance Timesheet'

    def _check_access(self):
        user = self.env.user
        if not user.active or user._is_public() or user.has_group('employee_portal_suite.group_attendance_only'):
            raise AccessError(_('Attendance timesheet printing is restricted to administrators.'))
        if not user.share and user.has_group('hr_attendance.group_hr_attendance_manager'):
            return
        self.env['absar.employee.admin.gateway']._actor('employee')

    def _company(self, company_id):
        self._check_access()
        try:
            company = self.env['res.company'].browse(int(company_id)).exists()
        except (TypeError, ValueError):
            raise ValidationError(_('Select a company.'))
        if len(company) != 1 or company not in self.env.user.company_ids:
            raise AccessError(_('Company is not available.'))
        return company

    def _employees(self, company_id):
        company = self._company(company_id)
        return self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('company_id', '=', company.id)], order='name, id')

    def _data(self, company_id, employee_id, date_from, date_to):
        company = self._company(company_id)
        try:
            employee_ident = int(employee_id)
            start_date, end_date = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        except (ValueError, TypeError):
            raise ValidationError(_('Select an employee and valid From / To dates.'))
        if not start_date or not end_date or start_date > end_date:
            raise ValidationError(_('The To date must be on or after the From date.'))
        employee = self.env['hr.employee'].sudo().with_context(active_test=False).search(
            [('id', '=', employee_ident), ('company_id', '=', company.id)], limit=1)
        if not employee:
            raise AccessError(_('Employee is not available in this company.'))
        timezone_name = self.env.user.tz or 'UTC'
        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            timezone_name, timezone = 'UTC', pytz.UTC
        # Match the administrator's visible attendance dates. Overnight records
        # belong to their check-in date and retain native Odoo worked_hours.
        lower = timezone.localize(datetime.combine(start_date, time.min))
        upper = timezone.localize(datetime.combine(end_date + timedelta(days=1), time.min))
        records = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('employee_id.company_id', '=', company.id),
            ('check_in', '>=', lower.astimezone(pytz.UTC).replace(tzinfo=None)),
            ('check_in', '<', upper.astimezone(pytz.UTC).replace(tzinfo=None)),
        ], order='check_in, id')
        grouped = {}
        total_hours = 0.0
        for attendance in records:
            check_in = pytz.UTC.localize(attendance.check_in).astimezone(timezone)
            check_out = pytz.UTC.localize(attendance.check_out).astimezone(timezone) if attendance.check_out else None
            hours = attendance.worked_hours if check_out else 0.0
            total_hours += hours
            grouped.setdefault(check_in.date(), []).append({
                'check_in': check_in.strftime('%H:%M'),
                'check_out': check_out.strftime('%H:%M') if check_out and check_out.date() == check_in.date() else check_out.strftime('%d/%m/%Y %H:%M') if check_out else '—',
                'hours': '{:.2f}'.format(hours) if check_out else '—',
                'note': _('Open check-in — excluded from total') if not check_out else '',
            })
        rows = []
        day = start_date
        while day <= end_date:
            for entry in grouped.get(day, [{'check_in': '—', 'check_out': '—', 'hours': '—', 'note': _('No attendance recorded')} ]):
                rows.append(dict(entry, date=day.strftime('%d/%m/%Y'), day=day.strftime('%A')))
            day += timedelta(days=1)
        return dict(company=company, employee=employee, rows=rows,
                    date_from=start_date.strftime('%d/%m/%Y'), date_to=end_date.strftime('%d/%m/%Y'),
                    timezone=timezone_name, total_hours='{:.2f}'.format(total_hours),
                    attendance_days=len(grouped), total_days=(end_date - start_date).days + 1)


class AttendanceTimesheetWizard(models.TransientModel):
    _name = 'absar.attendance.timesheet.wizard'
    _description = 'Print Attendance Timesheet'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one('hr.employee', required=True)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    has_preview = fields.Boolean(readonly=True)
    preview_line_ids = fields.One2many('absar.attendance.timesheet.preview.line', 'wizard_id', readonly=True)
    preview_timezone = fields.Char(string='Timezone', readonly=True)
    preview_total_hours = fields.Float(string='Total Worked Hours', digits=(16, 2), readonly=True)
    preview_attendance_days = fields.Integer(string='Days with Attendance', readonly=True)

    @api.onchange('company_id')
    def _onchange_company(self):
        self.employee_id = False

    @api.onchange('company_id', 'employee_id', 'date_from', 'date_to')
    def _onchange_preview_filters(self):
        self.has_preview = False
        self.preview_line_ids = [(5, 0, 0)]
        self.preview_timezone = False
        self.preview_total_hours = 0.0
        self.preview_attendance_days = 0

    def action_preview(self):
        self.ensure_one()
        values = self.env['absar.attendance.timesheet.service']._data(
            self.company_id.id, self.employee_id.id, self.date_from, self.date_to)
        self.write({
            'has_preview': True,
            'preview_timezone': values['timezone'],
            'preview_total_hours': float(values['total_hours']),
            'preview_attendance_days': values['attendance_days'],
            'preview_line_ids': [(5, 0, 0)] + [(0, 0, {
                'sequence': sequence,
                'attendance_date': datetime.strptime(row['date'], '%d/%m/%Y').date(),
                'weekday': row['day'], 'check_in_display': row['check_in'],
                'check_out_display': row['check_out'], 'hours_display': row['hours'],
                'note': row['note'],
            }) for sequence, row in enumerate(values['rows'])],
        })
        return {
            'type': 'ir.actions.act_window', 'name': _('Attendance Timesheet'),
            'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'target': 'new',
        }

    def action_print(self):
        self.ensure_one()
        service = self.env['absar.attendance.timesheet.service']
        service._data(self.company_id.id, self.employee_id.id, self.date_from, self.date_to)
        return self.env.ref('absar_portal_employee_admin.action_attendance_timesheet_pdf').report_action(
            self.employee_id, data={'company_id': self.company_id.id, 'employee_id': self.employee_id.id,
                                   'date_from': str(self.date_from), 'date_to': str(self.date_to)})


class AttendanceTimesheetPreviewLine(models.TransientModel):
    _name = 'absar.attendance.timesheet.preview.line'
    _description = 'Attendance Timesheet Preview Row'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('absar.attendance.timesheet.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer()
    attendance_date = fields.Date(string='Date', readonly=True)
    weekday = fields.Char(string='Day', readonly=True)
    check_in_display = fields.Char(string='Check In', readonly=True)
    check_out_display = fields.Char(string='Check Out', readonly=True)
    hours_display = fields.Char(string='Worked Hours', readonly=True)
    note = fields.Char(string='Notes', readonly=True)


class AttendanceTimesheetReport(models.AbstractModel):
    _name = 'report.absar_portal_employee_admin.attendance_timesheet_pdf'
    _description = 'Admin Attendance Timesheet PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        values = self.env['absar.attendance.timesheet.service']._data(
            data.get('company_id'), data.get('employee_id'), data.get('date_from'), data.get('date_to'))
        values.update(doc_ids=values['employee'].ids, doc_model='hr.employee', docs=values['employee'])
        return values
