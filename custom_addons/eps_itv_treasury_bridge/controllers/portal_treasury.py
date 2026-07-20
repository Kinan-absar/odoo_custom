from urllib.parse import quote

from odoo import http
from odoo.http import request
from odoo.exceptions import ValidationError, UserError


class PortalTreasury(http.Controller):
    VALID_FILTERS = {'pending', 'approved', 'held', 'rejected', 'all'}

    def _is_ceo(self):
        return request.env.user.has_group('employee_portal_suite.group_employee_portal_ceo')

    def _company_domain(self):
        return [('company_id', 'in', request.env.user.company_ids.ids)]

    def _get_run(self, run_id):
        run = request.env['cash.plan.run'].sudo().browse(run_id).exists()
        if not run or run.company_id not in request.env.user.company_ids:
            return False
        return run

    def _get_line(self, line_id):
        line = request.env['cash.plan.line'].sudo().browse(line_id).exists()
        if not line or line.company_id not in request.env.user.company_ids:
            return False
        return line

    def _payment_domain(self, status):
        domain = self._company_domain() + [('flow_type', '=', 'out')]
        if status == 'pending':
            domain.append(('ceo_decision', '=', 'pending'))
        elif status == 'approved':
            domain.append(('ceo_decision', 'in', ['approved', 'adjusted']))
        elif status == 'held':
            domain.append(('ceo_decision', '=', 'held'))
        elif status == 'rejected':
            domain.append(('ceo_decision', '=', 'rejected'))
        return domain

    @http.route('/my/employee/treasury', type='http', auth='user', website=True)
    def treasury_home(self, **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        return request.redirect('/my/employee/treasury/payments?status=pending')

    @http.route('/my/employee/treasury/payments', type='http', auth='user', website=True)
    def treasury_payment_approvals(self, status='pending', **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        status = (request.httprequest.args.get('status') or status or 'pending').strip().lower()
        if status not in self.VALID_FILTERS:
            status = 'pending'

        Line = request.env['cash.plan.line'].sudo()
        lines = Line.search(self._payment_domain(status), order='planned_date asc, priority desc, id desc')
        counts = {
            key: Line.search_count(self._payment_domain(key))
            for key in ('pending', 'approved', 'held', 'rejected', 'all')
        }
        return request.render('employee_portal_suite.portal_treasury_payment_list', {
            'lines': lines,
            'counts': counts,
            'current_status': status,
            'page_name': 'treasury_payments',
            'message': kw.get('message'),
            'error': kw.get('error'),
        })

    @http.route('/my/employee/treasury/plans', type='http', auth='user', website=True)
    def treasury_plans(self, **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        runs = request.env['cash.plan.run'].sudo().search(
            self._company_domain(), order='date_from desc, id desc'
        )
        return request.render('employee_portal_suite.portal_treasury_plan_list', {
            'runs': runs,
            'page_name': 'treasury_plans',
        })

    @http.route('/my/employee/treasury/plans/<int:run_id>', type='http', auth='user', website=True)
    def treasury_plan_detail(self, run_id, **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        run = self._get_run(run_id)
        if not run:
            return request.not_found()
        return request.render('employee_portal_suite.portal_treasury_plan_detail_clean_v3', {
            'run': run,
            'page_name': 'treasury_plans',
        })

    @http.route(
        '/my/employee/treasury/lines/<int:line_id>/review',
        type='http', auth='user', website=True, methods=['POST'], csrf=True
    )
    def treasury_line_review(self, line_id, **post):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        line = self._get_line(line_id)
        if not line:
            return request.not_found()
        decision = (post.get('decision') or '').strip().lower()
        try:
            if line.flow_type != 'out':
                raise UserError('Receipts do not require CEO approval.')
            amount_text = (post.get('approved_amount') or '').replace(',', '').strip()
            amount = float(amount_text) if amount_text else None
            line.action_ceo_decide(
                decision,
                approved_amount=amount,
                comment=post.get('comment'),
                reviewer=request.env.user,
            )
            target = {
                'approved': 'approved',
                'held': 'held',
                'rejected': 'rejected',
            }.get(decision, 'pending')
            message = {
                'approved': 'Payment approved successfully.',
                'held': 'Payment placed on hold.',
                'rejected': 'Payment rejected.',
            }.get(decision, 'Payment reviewed successfully.')
            return request.redirect(
                '/my/employee/treasury/payments?status=%s&message=%s'
                % (target, quote(message))
            )
        except (ValueError, ValidationError, UserError) as exc:
            return request.redirect(
                '/my/employee/treasury/payments?status=pending&error=%s' % quote(str(exc))
            )
