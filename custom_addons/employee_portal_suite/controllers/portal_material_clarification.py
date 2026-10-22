from odoo import http
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from urllib.parse import urlencode


class MaterialClarificationPortal(http.Controller):
    @http.route('/my/employee/material/requests/clarification/<string:operation>',
                type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def clarification(self, operation, **post):
        if operation not in ('request', 'reply'):
            return request.not_found()
        try:
            record_id = int(post.get('req_id', 0))
        except (ValueError, TypeError):
            return request.not_found()
        rec = request.env['material.request'].sudo().browse(record_id).exists()
        if not rec:
            return request.not_found()
        # Check the real signed-in user before allowing a sudo record to be used.
        own = rec.employee_id.user_id == request.env.user
        allowed = own if operation == 'reply' else rec._can_toggle_clarification()
        if not allowed:
            return request.not_found()
        target = '/my/employee/material/%s' % rec.id if own else '/my/employee/material/approvals/%s' % rec.id
        try:
            with request.env.cr.savepoint():
                if operation == 'request':
                    rec._request_clarification(post.get('question'))
                else:
                    rec._reply_clarification(post.get('answer'))
        except (UserError, ValidationError) as exc:
            return request.redirect(target + '?' + urlencode({'clarification_error': str(exc)}))
        return request.redirect(target + '?' + urlencode({'clarification_sent': operation}))
