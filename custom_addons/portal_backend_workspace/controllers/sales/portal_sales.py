from werkzeug.exceptions import Forbidden, NotFound
from odoo import http, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import float_compare
from odoo.osv import expression
from urllib.parse import urlencode
import json
import pytz
from datetime import datetime

from .sales_lines import SalesLinesMixin

BASE = '/my/workspace/sales'

class PortalSales(SalesLinesMixin, http.Controller):
    def _operator(self):
        return request.env.user.has_group('portal_backend_workspace.sales__group_portal_sales_user')

    def _allowed(self, approve=False, view=False):
        user = request.env.user
        if not user.sudo().with_company(user.company_id).employee_id or False:
            raise Forbidden()
        if view and user.has_group('portal_backend_workspace.sales__group_portal_sales_monitor'):
            return user
        if not user.has_group('portal_backend_workspace.sales__group_portal_sales_approver' if approve else 'portal_backend_workspace.sales__group_portal_sales_creator'):
            raise Forbidden()
        return user

    def _order(self, order_id, review=False):
        user = self._allowed(approve=review, view=not review)
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or order.company_id not in user.company_ids:
            raise NotFound()
        creator = order.pbw_portal_creator_id
        owner = order._pbw_sales_owner()
        is_monitor = user.has_group('portal_backend_workspace.sales__group_portal_sales_monitor')
        is_approver = user.has_group('portal_backend_workspace.sales__group_portal_sales_approver')
        if review:
            if not creator or user in (owner, creator):
                raise NotFound()
        elif not (self._operator() or owner == user or (creator and user in (creator,order.pbw_portal_submitter_id,order.pbw_order_requester_id)) or (is_approver and creator) or is_monitor):
            raise NotFound()
        return order

    def _editable(self, order):
        self._allowed()
        if not order.id:
            return
        if order.state in ('draft','sent') and order._pbw_is_sales_approver(request.env.user):
            return
        if self._operator() and order.state in ('draft','sent') and (not order.pbw_portal_creator_id or order.pbw_portal_review_state in ('draft','returned')):
            return
        if order._pbw_sales_owner() != request.env.user or order.pbw_portal_review_state not in ('draft','returned') or order.state not in ('draft','sent'):
            raise Forbidden()

    def _sales_date_local(self, value):
        if not value:return ''
        return pytz.UTC.localize(fields.Datetime.to_datetime(value)).astimezone(
            pytz.timezone(request.env.user.tz or 'UTC')).strftime('%Y-%m-%dT%H:%M:%S')

    def _sales_date_utc(self, value):
        if not value:raise ValidationError(_('Set the quotation/order date.'))
        try:
            local=datetime.fromisoformat(value)
            if local.tzinfo:raise ValueError()
            return pytz.timezone(request.env.user.tz or 'UTC').localize(local,is_dst=None).astimezone(pytz.UTC).replace(tzinfo=None)
        except (ValueError,TypeError,pytz.AmbiguousTimeError,pytz.NonExistentTimeError,pytz.UnknownTimeZoneError):
            raise ValidationError(_('Enter a valid quotation/order date in your user timezone.'))

    def _num(self, value, field='Amount'):
        try:
            result = float(value or 0)
        except (ValueError, TypeError):
            raise UserError(_('%s must be a number.') % field)
        if result < 0 or result != result or result == float('inf'):
            raise UserError(_('%s must be a nonnegative finite number.') % field)
        return result

    def _sales_company(self, partner=None):
        """Use an allowed contact's company, otherwise the active request company.

        Never accept an arbitrary browser company ID or silently create a record
        in the user's default company when its customer belongs to another one.
        """
        user = request.env.user
        if partner and partner.company_id:
            company = partner.company_id
        else:
            company = request.env.company
            # A website's default company need not be assigned to the portal user.
            if company not in user.company_ids:
                company = user.company_id
        if not company or company not in user.company_ids:
            raise Forbidden(_('The quotation company is not available to this user.'))
        return company

    def _partners(self, limit=500):
        partner_model = request.env['res.partner'].sudo()
        return partner_model.search(
            partner_model._pbw_sales_customer_domain(request.env.user.company_ids),
            limit=limit, order='name,id')

    def _projects(self, limit=500):
        return request.env['project.project'].sudo().search([
            ('active','=',True), '|', ('company_id','=',False),
            ('company_id','in',request.env.user.company_ids.ids)
        ], limit=limit, order='name')

    def _customer_projects(self, partner, order=None):
        """Customer projects, plus the authorized document's existing selection.

        Keep an older construction project's selection visible even if its
        customer link was subsequently changed. New choices remain filtered.
        """
        customer = partner.commercial_partner_id
        company = order.company_id if order is not None else self._sales_company(partner)
        projects = self._projects(limit=None).filtered(
            lambda p: p.partner_id and p.partner_id.commercial_partner_id == customer
            and (not p.company_id or p.company_id == company)
        )
        if order is not None:
            current = order._pbw_sales_project()
            if current and (not current.company_id or current.company_id == order.company_id):
                projects |= current
        return projects

    def _units(self):
        return request.env['uom.uom'].sudo().search([('active','=',True)],order='name')

    def _templates(self):
        """Optional proposal integrations supply their own templates through a bridge."""
        return []

    def _render(self, template, **kw):
        kw.setdefault('error', False)
        kw.setdefault('document_types', request.env['sale.order']._pbw_sales_document_types())
        if template == 'portal_backend_workspace.sales__sales_new':
            kw.setdefault('customer_source_labels', request.env['res.partner']._pbw_sales_customer_source_labels())
            kw.setdefault('quotation_company', self._sales_company())
        if template == 'portal_backend_workspace.sales__sales_detail' and kw.get('order'):
            kw['date_order_local']=self._sales_date_local(kw['order'].date_order)
            kw['line_boot_json'] = json.dumps(self._line_boot(kw['order']))
            kw['can_print'] = kw['order']._pbw_can_print_for(request.env.user)
            kw.update(kw['order']._pbw_review_permissions(request.env.user))
        return request.render(template, kw)

    def _list_view(self, *, monitor=False, queue=False, updates=False, params=None):
        user = self._allowed(approve=True) if queue else self._allowed(view=True)
        is_approver = user.has_group('portal_backend_workspace.sales__group_portal_sales_approver')
        is_monitor = user.has_group('portal_backend_workspace.sales__group_portal_sales_monitor')
        if monitor and not is_monitor:
            raise Forbidden()
        params = params or {}
        domain = [('company_id', 'in', user.company_ids.ids)]
        if queue:
            domain += [('pbw_portal_creator_id','!=',False), ('pbw_portal_creator_id','!=',user.id), ('create_uid','!=',user.id),
                       ('pbw_portal_submitter_id','!=',user.id),('pbw_order_requester_id','!=',user.id),
                       '|',('pbw_portal_review_state','=','submitted'),('pbw_order_review_state','=','requested'), ('state','in',['draft','sent'])]
        elif updates:
            domain += [('pbw_sales_decision_at','!=',False),'|','|',
                ('pbw_portal_creator_id','=',user.id),('pbw_portal_submitter_id','=',user.id),('pbw_order_requester_id','=',user.id)]
        elif not monitor and not self._operator():
            domain = expression.AND([domain, request.env['sale.order']._pbw_sales_owner_domain(user)])
        else:
            source = params.get('source', 'all')
            if source == 'portal':
                domain += [('pbw_portal_creator_id','!=',False)]
            elif source == 'backend':
                domain += [('pbw_portal_creator_id','=',False)]
            state = params.get('sales_state', 'all')
            if state == 'quotation':
                domain += [('state','in',['draft','sent'])]
            elif state == 'order':
                domain += [('state','in',['sale','done'])]
            elif state == 'cancel':
                domain += [('state','=','cancel')]
            review = params.get('review', 'all')
            if review in ('draft','submitted','approved','returned'):
                domain += [('pbw_portal_creator_id','!=',False),('pbw_portal_review_state','=',review)]
            elif review == 'direct':
                domain += [('pbw_order_review_state', '=', 'direct')]
            elif review == 'na':
                domain += [('pbw_portal_creator_id','=',False)]
        query = (params.get('q') or '').strip()[:120]
        if query:
            domain = expression.AND([domain, expression.OR([
                [('name','ilike',query)], [('partner_id.name','ilike',query)],
                request.env['sale.order']._pbw_sales_project_search_domain(query),
                [('user_id.name','ilike',query)]])])
        model = request.env['sale.order'].sudo()
        count = model.search_count(domain)
        per_page = 20
        try:
            page = max(1, min(int(params.get('page') or 1), max(1, (count + per_page - 1) // per_page)))
        except (ValueError,TypeError):
            page = 1
        orders = model.search(domain, limit=per_page, offset=(page-1)*per_page, order='pbw_sales_decision_at desc, id desc' if updates else 'date_order desc, id desc')
        pending_count = model.search_count([('company_id','in',user.company_ids.ids),
                ('pbw_portal_creator_id','!=',False),('pbw_portal_creator_id','!=',user.id),('create_uid','!=',user.id),
                ('pbw_portal_submitter_id','!=',user.id),('pbw_order_requester_id','!=',user.id),
                '|',('pbw_portal_review_state','=','submitted'),('pbw_order_review_state','=','requested'),('state','in',['draft','sent'])]) if is_approver else 0
        if queue or updates:
            request.env['pbw.notification.seen'].sudo()._mark_seen(user.id,'sales_approval' if queue else 'sales_review_update')
        base_url = BASE + ('/approvals' if queue else '/updates' if updates else '/monitor' if monitor else '')
        def page_url(target):
            args = {k:params.get(k) for k in ('q','source','sales_state','review') if params.get(k) and params.get(k) != 'all'}
            args['page'] = target
            return base_url + '?' + urlencode(args)
        return self._render('portal_backend_workspace.sales__sales_list', orders=orders,
            is_approver=is_approver, can_create=user.has_group('portal_backend_workspace.sales__group_portal_sales_creator'),
            is_monitor=is_monitor, monitoring=monitor, queue_only=queue, updates_only=updates, pending_count=pending_count,
            page=page, pages=max(1,(count+per_page-1)//per_page), total_count=count,
            previous_url=page_url(page-1), next_url=page_url(page+1), q=query,
            source=params.get('source','all'), sales_state=params.get('sales_state','all'),review=params.get('review','all'))

    @http.route(BASE+'/search-more',type='http',auth='user',methods=['POST'],csrf=True)
    def search_more(self,**post):
        self._allowed()
        data=json.loads(post.get('payload') or '{}');kind=data.get('kind');q=str(data.get('q') or '')[:120]
        allowed=[('active','=',True),'|',('company_id','=',False),('company_id','in',request.env.user.company_ids.ids)]
        if kind=='partner_id':
            model='res.partner'
            domain=request.env[model].sudo()._pbw_sales_customer_domain(request.env.user.company_ids)
        elif kind=='project_id':
            partner=request.env['res.partner'].sudo().browse(int(data.get('partner_id') or 0)).exists()
            if not partner or partner not in self._partners(limit=None):raise Forbidden()
            model='project.project';company=self._sales_company(partner)
            if data.get('order_id'):
                order=self._order(self._line_id(data['order_id']))
                if order.partner_id != partner:raise Forbidden()
                company=order.company_id
            domain=[('active','=',True), '|', ('company_id','=',False), ('company_id','=',company.id),
                    ('partner_id.commercial_partner_id','=',partner.commercial_partner_id.id)]
        elif kind=='uom_id':model='uom.uom';domain=[('active','=',True)]
        elif kind=='template_id':raise Forbidden()
        else:raise Forbidden()
        if q:domain=expression.AND([domain,[('name','ilike',q)]])
        offset=max(0,min(int(data.get('offset') or 0),100000))
        records=request.env[model].sudo().search(domain,order='name,id',offset=offset,limit=31)
        return request.make_json_response({'items':[{'id':r.id,'name':r.display_name,
            'customer_id':r.commercial_partner_id.id if kind=='partner_id' else r.partner_id.commercial_partner_id.id if kind=='project_id' else 0,
            'company_id':r.company_id.id if kind in ('partner_id','project_id') else 0,
            'company_name':r.company_id.name if kind=='partner_id' and r.company_id else ''} for r in records[:30]],'more':len(records)>30})

    @http.route(BASE, type='http', auth='user', website=True)
    def list_orders(self, **kw):
        user = request.env.user
        can_prepare = user.has_group('portal_backend_workspace.sales__group_portal_sales_creator')
        can_monitor = user.has_group('portal_backend_workspace.sales__group_portal_sales_monitor')
        if not can_prepare and can_monitor:
            return request.redirect(BASE + '/monitor')
        # My Quotations must never become a monitor-only landing page.
        self._allowed()
        return self._list_view(params=kw)

    @http.route(BASE + '/monitor', type='http', auth='user', website=True)
    def monitor_orders(self, **kw):
        return self._list_view(monitor=True, params=kw)

    @http.route(BASE + '/approvals', type='http', auth='user', website=True)
    def approval_queue(self, **kw):
        return self._list_view(queue=True, params=kw)

    @http.route(BASE+'/updates',type='http',auth='user',website=True)
    def review_updates(self, **kw):
        self._allowed()
        return self._list_view(updates=True,params=kw)

    @http.route(BASE + '/new', type='http', auth='user', website=True)
    def new_order(self, **kw):
        self._allowed()
        order,_vals=self._line_new_order({})
        return self._render('portal_backend_workspace.sales__sales_new',date_order_local=self._sales_date_local(fields.Datetime.now()),line_boot_json=json.dumps(self._line_boot(order)),partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units())

    @http.route(BASE + '/create', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def create_order(self, **post):
        user = self._allowed()
        try:
            with request.env.cr.savepoint():
                partner = request.env['res.partner'].sudo().browse(int(post.get('partner_id') or 0)).exists()
                if not partner or partner not in self._partners(limit=None):
                    raise UserError(_('Select an available customer.'))
                virtual, vals = self._line_new_order({'header': post}, required=True)
                order = self._line_env(virtual)['sale.order'].create(vals)
                order._pbw_sales_after_document_create(header=post)
                return request.redirect('%s/%s' % (BASE, order.id))
        except (ValueError, TypeError, UserError, ValidationError) as exc:
            return self._render('portal_backend_workspace.sales__sales_new',date_order_local=self._sales_date_local(fields.Datetime.now()),line_boot_json=json.dumps(self._line_boot(self._line_new_order({})[0])),partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units(),error=str(exc))

    @http.route(BASE + '/<int:order_id>', type='http', auth='user', website=True)
    def show_order(self, order_id, **kw):
        order = self._order(order_id)
        can_edit=False
        try:self._editable(order);can_edit=True
        except Forbidden:pass
        return self._render('portal_backend_workspace.sales__sales_detail', order=order, can_confirm=order._pbw_portal_can_confirm(request.env.user),
            can_edit=can_edit,
            can_review=(request.env.user.has_group('portal_backend_workspace.sales__group_portal_sales_approver') and order.pbw_portal_review_state=='submitted' and request.env.user not in (order.pbw_portal_creator_id,order.pbw_portal_submitter_id)),
            templates=self._templates(),projects=self._customer_projects(order.partner_id, order=order),units=self._units())

    @http.route(BASE+'/new-api/<string:operation>', type='http', auth='user', methods=['POST'], csrf=True)
    def new_line_api(self, operation, **post):
        self._allowed()
        return self._line_api(None, operation, post)

    @http.route(BASE + '/<int:order_id>/line-api/<string:operation>', type='http', auth='user', methods=['POST'], csrf=True)
    def line_api(self, order_id, operation, **post):
        return self._line_api(order_id, operation, post)

    @http.route(BASE + '/<int:order_id>/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def save_order(self, order_id, **post):
        order=self._order(order_id); self._editable(order)
        try:
            vals=self._line_header_values(order,post)
            order.sudo().write(vals)
        except (ValueError,ValidationError) as exc:
            return self._render('portal_backend_workspace.sales__sales_detail',order=order,can_edit=True,can_review=False,error=str(exc),templates=self._templates(),projects=self._customer_projects(order.partner_id, order=order),units=self._units())
        return request.redirect('%s/%s' % (BASE, order.id))

    @http.route(BASE + '/<int:order_id>/line/add', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_line(self, order_id, **post):
        order=self._order(order_id); self._editable(order)
        try:
            name=(post.get('description') or '').strip()
            if not name or len(name)>8000:
                raise UserError(_('Enter a description (maximum 8000 characters).'))
            qty=self._num(post.get('qty'), 'Quantity')
            rate=self._num(post.get('rate'), 'Unit rate')
            unit_id=int(post.get('uom_id') or 0)
            unit=request.env['uom.uom'].sudo().browse(unit_id).exists() if unit_id else request.env.ref('uom.product_uom_unit',raise_if_not_found=False)
            if not unit or (unit_id and unit not in self._units()): raise UserError(_('Invalid unit of measure.'))
            vals={'order_id':order.id,'name':name,'product_uom_qty':qty,'price_unit':rate,'product_uom':unit.id}
            request.env['sale.order.line'].sudo().create(vals)
        except (UserError,ValidationError) as exc:
            if request.httprequest.headers.get('X-APS-Inline') == '1':
                return request.make_response(json.dumps({'ok':False,'error':str(exc)}), headers=[('Content-Type','application/json')], status=400)
            return request.redirect('%s/%s?error=add_line' % (BASE,order.id))
        if request.httprequest.headers.get('X-APS-Inline') == '1':
            line = order.order_line.sorted(key=lambda l:l.id)[-1]
            return request.make_response(json.dumps({
                'ok':True,'id':line.id,'description':line.name,
                'unit':line.product_uom.name,'qty':line.product_uom_qty,
                'rate':line.price_unit,'subtotal':line.price_subtotal,
                'total':order.amount_untaxed,'currency':order.currency_id.name,
                'delete_url':'%s/%s/line/%s/delete' % (BASE,order.id,line.id),
            }),headers=[('Content-Type','application/json')])
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/line/<int:line_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def delete_line(self,order_id,line_id,**post):
        order=self._order(order_id); self._editable(order)
        line=order.order_line.filtered(lambda l:l.id==line_id)
        if not line: raise NotFound()
        line.sudo().unlink()
        return request.redirect('%s/%s' % (BASE,order.id))










    @http.route(BASE + '/<int:order_id>/workflow', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def workflow(self,order_id,**post):
        order=self._order(order_id)
        action=post.get('action')
        if action=='confirm_direct':
            self._allowed(approve=True)
            order._pbw_confirm_own_quotation()
        elif action=='request_order':
            order.action_pbw_request_order()
        elif action=='submit':
            self._editable(order)
            order._pbw_portal_submit()
            return request.redirect(BASE)
        elif action in ('approve','return','approve_order','return_order'):
            self._allowed(approve=True)
            if action=='approve':order.action_pbw_portal_approve()
            elif action=='approve_order':order.action_pbw_approve_order()
            else:
                note=(post.get('note') or '').strip()
                if not note:raise Forbidden()
                order.sudo().write({'pbw_portal_review_note':note[:3000]})
                if action=='return_order':order.action_pbw_return_order()
                else:order.action_pbw_portal_return()
        else: raise Forbidden()
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/pdf', type='http', auth='user', website=True)
    def pdf(self,order_id,**kw):
        order=self._order(order_id)
        if not order._pbw_can_print_for(request.env.user): raise Forbidden()
        report='sale.action_report_saleorder'
        content,_=request.env['ir.actions.report'].sudo()._render_qweb_pdf(report,[order.id])
        return request.make_response(content,headers=[('Content-Type','application/pdf'),('Content-Disposition','inline; filename="%s.pdf"' % order.name.replace('/','-'))])
