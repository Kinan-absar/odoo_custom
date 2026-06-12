# -*- coding: utf-8 -*-

import base64

from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import MissingError


class EmployeePortalReports(CustomerPortal):

    def _portal_report_domain(self):
        return [
            ('active', '=', True),
            ('allowed_group_ids', 'in', request.env.user.groups_id.ids),
        ]

    def _get_accessible_report(self, report_id):
        report = request.env['portal.report.document'].sudo().browse(report_id)
        if not report.exists() or not report._portal_user_can_access(request.env.user):
            raise MissingError('Report not found or not available for your account.')
        return report

    @http.route('/my/employee/reports', type='http', auth='user', website=True)
    def portal_reports_list(self, page=1, **kw):
        Report = request.env['portal.report.document'].sudo()
        domain = self._portal_report_domain()
        total = Report.search_count(domain)
        pager = portal_pager(
            url='/my/employee/reports',
            total=total,
            page=page,
            step=20,
        )
        reports = Report.search(domain, order='date desc, id desc', limit=20, offset=pager['offset'])
        return request.render('employee_portal_suite.portal_reports_list', {
            'reports': reports,
            'pager': pager,
            'page_name': 'portal_reports',
        })

    @http.route('/my/employee/reports/<int:report_id>', type='http', auth='user', website=True)
    def portal_report_detail(self, report_id, **kw):
        report = self._get_accessible_report(report_id)
        return request.render('employee_portal_suite.portal_report_detail', {
            'report': report,
            'page_name': 'portal_reports',
        })

    @http.route('/my/employee/reports/<int:report_id>/view', type='http', auth='user', website=True)
    def portal_report_view(self, report_id, **kw):
        report = self._get_accessible_report(report_id)
        if not report.file:
            raise MissingError('No PDF file is attached to this report.')

        filename = report.filename or (report.name + '.pdf')
        content = base64.b64decode(report.file)
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(content)),
            ('Content-Disposition', 'inline; filename="%s"' % filename.replace('"', '')),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)

    @http.route('/my/employee/reports/<int:report_id>/download', type='http', auth='user', website=True)
    def portal_report_download(self, report_id, **kw):
        report = self._get_accessible_report(report_id)
        if not report.file:
            raise MissingError('No PDF file is attached to this report.')

        filename = report.filename or (report.name + '.pdf')
        content = base64.b64decode(report.file)
        headers = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(content)),
            ('Content-Disposition', http.content_disposition(filename)),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)
