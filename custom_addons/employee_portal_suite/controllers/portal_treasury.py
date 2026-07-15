from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError


class PortalTreasury(http.Controller):
    def _is_ceo(self):
        return request.env.user.has_group('employee_portal_suite.group_employee_portal_ceo')

    def _company_domain(self):
        return [('company_id', 'in', request.env.user.company_ids.ids)]

    def _get_run(self, run_id):
        run = request.env['cash.plan.run'].sudo().browse(run_id).exists()
        if not run or run.company_id not in request.env.user.company_ids:
            return False
        return run

    @http.route(['/my/employee/treasury', '/my/employee/treasury/plans'], type='http', auth='user', website=True)
    def treasury_plans(self, status='pending', **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        domain = self._company_domain()
        if status == 'pending':
            domain += [('ceo_status', '=', 'pending')]
        elif status == 'approved':
            domain += [('state', 'in', ('approved', 'in_progress', 'done'))]
        elif status == 'draft':
            domain += [('state', '=', 'draft')]
        runs = request.env['cash.plan.run'].sudo().search(domain, order='date_from desc, id desc')
        return request.render('employee_portal_suite.portal_treasury_plan_list', {
            'runs': runs, 'current_status': status, 'page_name': 'treasury',
        })

    @http.route('/my/employee/treasury/plans/<int:run_id>', type='http', auth='user', website=True)
    def treasury_plan_detail(self, run_id, **kw):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        run = self._get_run(run_id)
        if not run:
            return request.not_found()
        # Repair records created by older workflow versions: pending lines must be actionable.
        pending_lines = run.line_ids.filtered(lambda line: line.state != 'cancel' and line.ceo_decision == 'pending')
        if pending_lines and (run.state != 'submitted' or run.ceo_status != 'pending'):
            run.sudo().write({'state': 'submitted', 'ceo_status': 'pending'})
        return request.render('employee_portal_suite.portal_treasury_plan_detail', {
            'run': run, 'page_name': 'treasury', 'message': kw.get('message'), 'error': kw.get('error'),
        })

    @http.route('/my/employee/treasury/lines/<int:line_id>/review', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def treasury_line_review(self, line_id, **post):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        line = request.env['cash.plan.line'].sudo().browse(line_id).exists()
        if not line or line.company_id not in request.env.user.company_ids:
            return request.not_found()
        try:
            decision = post.get('decision')
            amount_text = (post.get('approved_amount') or '').replace(',', '').strip()
            amount = float(amount_text) if amount_text else None
            line.action_ceo_decide(decision, approved_amount=amount, comment=post.get('comment'), reviewer=request.env.user)
            return request.redirect('/my/employee/treasury/plans/%s?message=Line reviewed successfully' % line.run_id.id)
        except (ValueError, ValidationError, UserError) as exc:
            return request.redirect('/my/employee/treasury/plans/%s?error=%s' % (line.run_id.id, str(exc)))

    @http.route('/my/employee/treasury/plans/<int:run_id>/approve', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def treasury_plan_approve(self, run_id, **post):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        run = self._get_run(run_id)
        if not run:
            return request.not_found()
        try:
            run.sudo().write({'ceo_comment': post.get('comment') or False, 'ceo_reviewed_by': request.env.user.id, 'ceo_reviewed_date': False})
            # Set date separately to avoid portal-user ACL interaction.
            from odoo import fields
            run.sudo().write({'ceo_reviewed_date': fields.Datetime.now()})
            run.sudo().with_context(ceo_portal_approval=True).action_approve()
            return request.redirect('/my/employee/treasury/plans/%s?message=Weekly cash plan approved' % run.id)
        except (ValidationError, UserError) as exc:
            return request.redirect('/my/employee/treasury/plans/%s?error=%s' % (run.id, str(exc)))


    @http.route('/my/employee/treasury/plans/<int:run_id>/reject', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def treasury_plan_reject(self, run_id, **post):
        if not self._is_ceo():
            return request.redirect('/my/employee')
        run = self._get_run(run_id)
        if not run:
            return request.not_found()
        try:
            run.sudo().action_ceo_reject(comment=post.get('comment'), reviewer=request.env.user)
            return request.redirect('/my/employee/treasury/plans/%s?message=Weekly cash plan rejected' % run.id)
        except (ValidationError, UserError) as exc:
            return request.redirect('/my/employee/treasury/plans/%s?error=%s' % (run.id, str(exc)))
