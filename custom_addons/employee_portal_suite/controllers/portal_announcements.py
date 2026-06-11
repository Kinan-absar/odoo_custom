# -*- coding: utf-8 -*-

import base64
import mimetypes

from odoo import http
from odoo.exceptions import MissingError
from odoo.http import request


class EmployeePortalAnnouncements(http.Controller):

    def _get_accessible_announcement_attachment(self, announcement_id, attachment_id, target='portal'):
        announcement = request.env['portal.announcement'].sudo().browse(announcement_id)
        if not announcement.exists() or not announcement._user_can_access(request.env.user, target=target):
            raise MissingError('Announcement not found or not available for your account.')

        attachment = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not attachment.exists() or attachment not in announcement.attachment_ids:
            raise MissingError('Attachment not found or not available for your account.')

        if not attachment.datas:
            raise MissingError('Attachment content is not available.')

        return announcement, attachment

    @http.route('/my/employee/announcements/<int:announcement_id>/attachments/<int:attachment_id>/view', type='http', auth='user', website=True)
    def portal_announcement_attachment_view(self, announcement_id, attachment_id, **kw):
        announcement, attachment = self._get_accessible_announcement_attachment(announcement_id, attachment_id, target='portal')
        content = base64.b64decode(attachment.datas)
        filename = attachment.name or 'attachment'
        mimetype = attachment.mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = [
            ('Content-Type', mimetype),
            ('Content-Length', len(content)),
            ('Content-Disposition', 'inline; filename="%s"' % filename.replace('"', '')),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)

    @http.route('/my/employee/announcements/<int:announcement_id>/attachments/<int:attachment_id>/download', type='http', auth='user', website=True)
    def portal_announcement_attachment_download(self, announcement_id, attachment_id, **kw):
        announcement, attachment = self._get_accessible_announcement_attachment(announcement_id, attachment_id, target='portal')
        content = base64.b64decode(attachment.datas)
        filename = attachment.name or 'attachment'
        mimetype = attachment.mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = [
            ('Content-Type', mimetype),
            ('Content-Length', len(content)),
            ('Content-Disposition', http.content_disposition(filename)),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)
    @http.route('/employee_portal_suite/announcements/<int:announcement_id>/attachments/<int:attachment_id>/view', type='http', auth='user')
    def backend_announcement_attachment_view(self, announcement_id, attachment_id, **kw):
        announcement, attachment = self._get_accessible_announcement_attachment(announcement_id, attachment_id, target='backend')
        content = base64.b64decode(attachment.datas)
        filename = attachment.name or 'attachment'
        mimetype = attachment.mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = [
            ('Content-Type', mimetype),
            ('Content-Length', len(content)),
            ('Content-Disposition', 'inline; filename="%s"' % filename.replace('"', '')),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)

    @http.route('/employee_portal_suite/announcements/<int:announcement_id>/attachments/<int:attachment_id>/download', type='http', auth='user')
    def backend_announcement_attachment_download(self, announcement_id, attachment_id, **kw):
        announcement, attachment = self._get_accessible_announcement_attachment(announcement_id, attachment_id, target='backend')
        content = base64.b64decode(attachment.datas)
        filename = attachment.name or 'attachment'
        mimetype = attachment.mimetype or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        headers = [
            ('Content-Type', mimetype),
            ('Content-Length', len(content)),
            ('Content-Disposition', http.content_disposition(filename)),
            ('X-Content-Type-Options', 'nosniff'),
        ]
        return request.make_response(content, headers=headers)

