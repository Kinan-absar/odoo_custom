"""Read-only desktop dashboard using existing owner domains and approval providers."""
from datetime import datetime, time, timedelta
import pytz
from odoo import http, fields
from odoo.http import request
from .portal_main import EmployeePortalMain

COLORS = {'draft': '#94a3b8', 'pending': '#f5a623', 'approved': '#087f83', 'rejected': '#dc6b73'}


def status_totals(groups):
    counts = dict.fromkeys(COLORS, 0)
    for rows in groups:
        for row in rows:
            state = row.get('state')
            bucket = state if state in ('draft', 'approved', 'rejected') else 'pending'
            counts[bucket] += row.get('state_count', row.get('__count', 0))
    return counts


def week_windows(today, timezone):
    zone = pytz.timezone(timezone or 'UTC')
    monday = today - timedelta(days=today.weekday())
    for index in range(8):
        start = monday - timedelta(weeks=7-index)
        end = start + timedelta(days=7)
        utc = lambda day: zone.localize(datetime.combine(day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        yield start.strftime('%d %b'), fields.Datetime.to_string(utc(start)), fields.Datetime.to_string(utc(end))


class EmployeePortalVisualDashboard(EmployeePortalMain):
    @http.route()
    def employee_portal_dashboard(self, **kw):
        response = super().employee_portal_dashboard(**kw)
        context = getattr(response, 'qcontext', None)
        if context is None:
            return response  # Preserve internal/attendance-only/no-employee redirects.
        user = request.env.user
        if not user.share or not user.employee_id or user.has_group('employee_portal_suite.group_attendance_only'):
            return response
        context['visual_dashboard'] = self._visual_dashboard(user)
        return response

    def _visual_dashboard(self, user):
        employee = user.employee_id
        sources = [
            (request.env['employee.request'].sudo(), [('employee_id', '=', employee.id)]),
            (request.env['material.request'].sudo(), [('employee_id.user_id', '=', user.id)]),
        ]
        counts = status_totals([model.read_group(domain, ['state'], ['state']) for model, domain in sources])
        today = fields.Date.context_today(user)
        weeks = []
        for label, start, end in week_windows(today, user.tz or 'UTC'):
            values = [model.search_count(domain + [('create_date', '>=', start), ('create_date', '<', end)])
                      for model, domain in sources]
            weeks.append({'label': label, 'employee': values[0], 'material': values[1], 'total': sum(values)})
        summary = request.env['portal.report.seen'].sudo()._get_notification_summary(user)
        queues = []
        for key in ('er_approval', 'mr_approval', 'sign_request', 'purchase_approval', 'sales_approval'):
            item = summary.get(key)
            if item:
                queues.append({'label': str(item['label']), 'count': item['count'], 'url': item['url']})
        # The Accounting gateway retains its journal/company/role restrictions.
        if 'absar.portal.accounting.service' in request.env and self._safe_has_group('absar_portal_accounting.group_approver'):
            service = request.env['absar.portal.accounting.service']
            service._actor('approver')
            for company in user.sudo().company_ids:
                company = service._company(company.id)
                for kind in ('bills', 'refunds', 'journals', 'payments', 'receipts'):
                    model, title, _ = service._kind(kind)
                    domain = service._domain(company, kind) + [
                        ('state', '=', 'draft'), ('portal_accounting_review', '=', 'submitted'),
                        ('portal_accounting_issuer_id', '!=', user.id)]
                    count = service._env(company)[model].search_count(domain)
                    if count:
                        queues.append({'label': '%s · %s' % (title, company.name), 'count': count,
                                       'url': '/my/employee/accounting/%s?company_id=%s&status=submitted' % (kind, company.id)})
        cash = []
        if ('cash.plan.run' in request.env and
                self._safe_has_group('employee_portal_suite.group_employee_portal_ceo') and
                request.env.ref('eps_itv_treasury_bridge.employee_portal_dashboard_treasury', raise_if_not_found=False)):
            company_ids = user.sudo().company_ids.ids
            pending = request.env['cash.plan.line'].sudo().search_count([
                ('company_id', 'in', company_ids), ('flow_type', '=', 'out'), ('ceo_decision', '=', 'pending')])
            queues.append({'label': 'Payment Reviews', 'count': pending, 'url': '/my/employee/treasury/payments?status=pending'})
            runs = request.env['cash.plan.run'].sudo().search([
                ('company_id', 'in', company_ids), ('date_from', '<=', today), ('date_to', '>=', today)],
                order='date_from desc, id desc', limit=6)
            for run in runs:
                cash.append({'name': run.name, 'company': run.company_id.name,
                             'currency': run.currency_id.name, 'planned': run.forecast_outflow,
                             'actual': run.actual_outflow, 'url': '/my/employee/treasury/plans/%s' % run.id})
        total = sum(counts.values())
        offset = 0
        segments = []
        for key, label in [('draft', 'Draft'), ('pending', 'In Approval'), ('approved', 'Approved'), ('rejected', 'Rejected')]:
            value = counts[key]
            angle = value / total * 360 if total else 0
            segments.append('%s %.4fdeg %.4fdeg' % (COLORS[key], offset, offset+angle))
            offset += angle
        return {'counts': counts, 'total': total, 'weeks': weeks, 'queues': queues, 'cash': cash,
                'pending': sum(q['count'] for q in queues),
                'gradient': 'conic-gradient(%s)' % ','.join(segments) if total else '#edf2f4',
                'colors': COLORS, 'today': today.strftime('%A, %d %B %Y'),
                'updated': fields.Datetime.context_timestamp(user, fields.Datetime.now()).strftime('%H:%M'),
                'week_max': max([w['total'] for w in weeks] + [1]),
                'queue_max': max([q['count'] for q in queues] + [1])}
