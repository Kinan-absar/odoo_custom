import json
from werkzeug.exceptions import Forbidden, NotFound, BadRequest
from odoo import http
from odoo.http import request

BASE = '/my/employee/purchase'


class PortalPurchasePrepare(http.Controller):
    def _role(self, approver=False):
        user = request.env.user
        group = 'group_portal_purchase_approver' if approver else 'group_portal_purchase_preparer'
        if not user.has_group('absar_portal_purchase_monitor.' + group) or not user.employee_id:
            raise Forbidden()
        return user

    def _mine(self, po_id, editable=True):
        user = self._role()
        po = request.env['purchase.order'].sudo().browse(po_id).exists()
        if not po or po.company_id not in user.company_ids or po.absar_portal_preparer_id.id != user.id:
            raise NotFound()
        if editable and (po.state not in ('draft', 'sent') or po.absar_portal_review_state not in (False, 'draft', 'returned')):
            raise Forbidden()
        return po

    def _models(self, user):
        cid = user.company_id.id
        suppliers = request.env['res.partner'].sudo().search([('supplier_rank', '>', 0), ('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', cid)], order='name', limit=300)
        products = request.env['product.product'].sudo().search([('purchase_ok', '=', True), ('active', '=', True), '|', ('company_id', '=', False), ('company_id', '=', cid)], order='name', limit=500)
        accounts = request.env['account.account'].sudo().search([('deprecated', '=', False), ('company_ids', 'in', [cid]), ('account_type', 'in', ['expense','expense_direct_cost','expense_depreciation','asset_fixed','asset_current'])], order='code', limit=500) if 'company_ids' in request.env['account.account']._fields else request.env['account.account'].sudo().search([('deprecated','=',False),('company_id','=',cid),('account_type','in',['expense','expense_direct_cost','expense_depreciation','asset_fixed','asset_current'])], order='code', limit=500)
        analytics = request.env['account.analytic.account'].sudo().search(['|', ('company_id', '=', False), ('company_id', '=', cid)], order='name', limit=500)
        projects = request.env['project.project'].sudo().search(['|', ('company_id', '=', False), ('company_id', '=', cid)], order='name', limit=300) if 'project.project' in request.env else request.env['purchase.order'].browse()
        return dict(suppliers=suppliers, products=products, accounts=accounts, analytics=analytics, projects=projects, currencies=request.env['res.currency'].sudo().search([('active','=',True)], order='name'), buyers=request.env['res.users'].sudo().search([('share','=',False),('company_ids','in',[cid])], order='name', limit=200))

    @http.route(BASE, type='http', auth='user', website=True)
    def mine(self, **kw):
        user = self._role()
        pos = request.env['purchase.order'].sudo().search([('absar_portal_preparer_id', '=', user.id), ('company_id', 'in', user.company_ids.ids)], order='id desc', limit=60)
        return request.render('absar_portal_purchase_monitor.purchase_prepare_list', dict(orders=pos))

    @http.route(BASE + '/new', type='http', auth='user', website=True, methods=['GET','POST'], csrf=True)
    def new(self, **post):
        user = self._role()
        if request.httprequest.method == 'POST':
            try:
                partner_id = int(post.get('partner_id') or 0)
            except ValueError:
                raise BadRequest()
            partner = request.env['res.partner'].sudo().browse(partner_id).exists()
            if not partner or partner.supplier_rank <= 0 or (partner.company_id and partner.company_id != user.company_id):
                raise BadRequest('Choose an existing supplier.')
            project_id = int(post.get('project_id') or 0)
            project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
            if project_id and (not project or (project.company_id and project.company_id != user.company_id)):
                raise BadRequest('Invalid project.')
            po = request.env['purchase.order'].sudo().with_company(user.company_id).create({
                'partner_id': partner.id, 'company_id': user.company_id.id,
                'origin': (post.get('origin') or '')[:200],
                'absar_portal_project_id': project.id if project else False,
                'absar_portal_preparer_id': user.id,
                'absar_portal_review_state': 'draft',
            })
            return request.redirect(BASE + '/%d' % po.id)
        return request.render('absar_portal_purchase_monitor.purchase_prepare_new', self._models(user))

    @http.route(BASE + '/<int:po_id>', type='http', auth='user', website=True)
    def detail(self, po_id, **kw):
        po = self._mine(po_id, editable=False)
        user = request.env.user
        vals = self._models(user)
        vals.update(po=po, editable=po.state in ('draft', 'sent') and po.absar_portal_review_state in (False,'draft','returned'))
        return request.render('absar_portal_purchase_monitor.purchase_prepare_detail', vals)

    @http.route(BASE + '/approvals', type='http', auth='user', website=True)
    def approvals(self, **kw):
        user = self._role(approver=True)
        pos = request.env['purchase.order'].sudo().search([('absar_portal_review_state','=','submitted'), ('company_id','in',user.company_ids.ids), ('absar_portal_preparer_id','!=',user.id)], limit=60, order='id desc')
        return request.render('absar_portal_purchase_monitor.purchase_approval_list', {'orders': pos})

    @http.route(BASE + '/approvals/<int:po_id>/<string:action>', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def review(self, po_id, action, **post):
        user = self._role(approver=True)
        po = request.env['purchase.order'].sudo().browse(po_id).exists()
        if not po or po.company_id not in user.company_ids or po.absar_portal_preparer_id.id == user.id or po.absar_portal_review_state != 'submitted':
            raise Forbidden()
        if action == 'approve':
            po.action_absar_portal_approve()
        elif action == 'return':
            po.write({'absar_portal_review_note': (post.get('note') or '')[:500]})
            po.action_absar_portal_return()
        else:
            raise NotFound()
        return request.redirect(BASE + '/approvals')

    @http.route(BASE + '/<int:po_id>/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def save_header(self, po_id, **post):
        po = self._mine(po_id)
        partner = request.env['res.partner'].sudo().browse(int(post.get('partner_id') or 0)).exists()
        if not partner or partner.supplier_rank <= 0 or (partner.company_id and partner.company_id != po.company_id):
            raise BadRequest('Select a valid supplier.')
        project_id = int(post.get('project_id') or 0)
        project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
        if project_id and (not project or project.company_id and project.company_id != po.company_id):
            raise BadRequest('Invalid project.')
        vals = {'partner_id': partner.id, 'absar_portal_project_id': project.id if project else False,
                'origin': (post.get('origin') or '')[:200], 'notes': (post.get('notes') or '')[:10000]}
        if post.get('date_planned'):
            vals['date_planned'] = post['date_planned']
        if post.get('partner_ref'):
            vals['partner_ref'] = post['partner_ref'][:200]
        if post.get('user_id'):
            buyer = request.env['res.users'].sudo().browse(int(post['user_id'])).exists()
            if not buyer or buyer.share or po.company_id not in buyer.company_ids:
                raise BadRequest('Invalid buyer.')
            vals['user_id'] = buyer.id
        po.with_company(po.company_id).sudo().write(vals)
        return request.redirect(BASE + '/%d' % po.id)

    @http.route(BASE + '/<int:po_id>/line/<int:line_id>/remove', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def remove_line(self, po_id, line_id, **post):
        po = self._mine(po_id)
        line = po.order_line.filtered(lambda x: x.id == line_id)
        if not line:
            raise NotFound()
        line.sudo().unlink()
        return request.redirect(BASE + '/%d' % po.id)

    @http.route(BASE + '/<int:po_id>/product', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def product(self, po_id, **post):
        po = self._mine(po_id)
        name = (post.get('name') or '').strip()[:150]
        if not name:
            raise BadRequest('Product name required.')
        vals = {'name': name, 'purchase_ok': True, 'sale_ok': False, 'type': 'consu', 'company_id': po.company_id.id}
        product = request.env['product.product'].sudo().with_company(po.company_id).create(vals)
        return request.redirect(BASE + '/%d?created_product=%d' % (po.id, product.id))

    @http.route(BASE + '/<int:po_id>/line', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_line(self, po_id, **post):
        po = self._mine(po_id)
        try:
            product_id = int(post.get('product_id') or 0)
            qty = float(post.get('qty') or 0)
            price = float(post.get('price') or 0)
            account_id = int(post.get('account_id') or 0)
            analytic_id = int(post.get('analytic_id') or 0)
            analytic_pct = float(post.get('analytic_percent') or 100)
        except (TypeError, ValueError):
            raise BadRequest('Invalid quantity, price, or account.')
        if qty <= 0 or price < 0 or not 0 <= analytic_pct <= 100:
            raise BadRequest('Invalid quantity, price, or analytic percentage.')
        product = request.env['product.product'].sudo().browse(product_id).exists()
        if not product or not product.purchase_ok or product.company_id and product.company_id != po.company_id:
            raise BadRequest('Choose a permitted purchasable product.')
        vals = {'order_id': po.id, 'product_id': product.id,
                'name': (post.get('description') or product.display_name)[:2000],
                'product_qty': qty, 'price_unit': price,
                'product_uom': product.uom_po_id.id or product.uom_id.id,
                'date_planned': po.date_order or __import__('datetime').datetime.now()}
        line_model = request.env['purchase.order.line'].sudo().with_company(po.company_id)
        if account_id:
            account = request.env['account.account'].sudo().browse(account_id).exists()
            if not account or account.deprecated or account.account_type not in ('expense','expense_direct_cost','expense_depreciation','asset_fixed','asset_current') or (hasattr(account,'company_ids') and po.company_id not in account.company_ids) or (hasattr(account,'company_id') and account.company_id != po.company_id):
                raise BadRequest('Invalid expense account.')
            vals['absar_expense_account_id'] = account.id
        if analytic_id:
            analytic = request.env['account.analytic.account'].sudo().browse(analytic_id).exists()
            if not analytic or analytic.company_id and analytic.company_id != po.company_id:
                raise BadRequest('Invalid analytic account.')
            if 'analytic_distribution' in line_model._fields:
                vals['analytic_distribution'] = {str(analytic.id): analytic_pct}
        line_model.create(vals)
        return request.redirect(BASE + '/%d' % po.id)

    @http.route(BASE + '/<int:po_id>/submit', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit(self, po_id, **post):
        po = self._mine(po_id)
        if not po.order_line.filtered(lambda l: not l.display_type):
            raise BadRequest('Add a line before submission.')
        po.write({'absar_portal_review_state': 'submitted'})
        po.message_post(body='Portal RFQ submitted for purchase approval.')
        # Notify internal approvers by inbox message and activity.
        group = request.env.ref('absar_portal_purchase_monitor.group_portal_purchase_approver')
        for approver in group.users.filtered(lambda u: not u.share and po.company_id in u.company_ids and u != request.env.user):
            po.activity_schedule('mail.mail_activity_data_todo', user_id=approver.id, summary='Review portal RFQ %s' % po.name)
        return request.redirect(BASE + '/%d' % po.id)
