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

BASE = '/my/employee/sales'

class PortalSales(SalesLinesMixin, http.Controller):
    def _operator(self):
        return request.env.user.has_group('absar_portal_sales.group_portal_sales_user')

    def _allowed(self, approve=False, view=False):
        user = request.env.user
        if not user.employee_id or user.has_group('employee_portal_suite.group_attendance_only'):
            raise Forbidden()
        if view and user.has_group('absar_portal_sales.group_portal_sales_monitor'):
            return user
        if not user.has_group('absar_portal_sales.group_portal_sales_approver' if approve else 'absar_portal_sales.group_portal_sales_creator'):
            raise Forbidden()
        return user

    def _order(self, order_id, review=False):
        user = self._allowed(approve=review, view=not review)
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or order.company_id not in user.company_ids:
            raise NotFound()
        creator = order.absar_portal_creator_id
        is_monitor = user.has_group('absar_portal_sales.group_portal_sales_monitor')
        is_approver = user.has_group('absar_portal_sales.group_portal_sales_approver')
        if review:
            if not creator or creator.id == user.id:
                raise NotFound()
        elif not (self._operator() or (creator and user in (creator,order.absar_portal_submitter_id,order.absar_order_requester_id)) or (is_approver and creator) or is_monitor):
            raise NotFound()
        return order

    def _editable(self, order):
        if not order.id:
            self._allowed()
            return
        if self._operator() and order.state in ('draft','sent') and (not order.absar_portal_creator_id or order.absar_portal_review_state in ('draft','returned')):
            return
        if order.absar_portal_creator_id.id != request.env.user.id or order.absar_portal_review_state not in ('draft','returned') or order.state not in ('draft','sent'):
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

    def _partners(self, limit=500):
        return request.env['res.partner'].sudo().search([
            ('absar_is_sales_customer','=',True), ('active','=',True),
            '|', ('company_id','=',False), ('company_id','in',request.env.user.company_ids.ids)
        ], limit=limit, order='name')

    def _projects(self, limit=500):
        return request.env['project.project'].sudo().search([
            ('active','=',True), '|', ('company_id','=',False),
            ('company_id','in',request.env.user.company_ids.ids)
        ], limit=limit, order='name')

    def _customer_projects(self, partner):
        """Only company-compatible projects assigned to this customer's commercial entity."""
        customer = partner.commercial_partner_id
        return self._projects(limit=None).filtered(
            lambda p: p.partner_id and p.partner_id.commercial_partner_id == customer
        )

    def _units(self):
        return request.env['uom.uom'].sudo().search([('active','=',True)],order='name')

    def _templates(self):
        return request.env['absar.proposal.template'].sudo().search([
            ('active','=',True), '|', ('company_id','=',False), ('company_id','in',request.env.user.company_ids.ids)
        ], order='name')

    def _render(self, template, **kw):
        kw.setdefault('error', False)
        if template == 'absar_portal_sales.sales_detail' and kw.get('order'):
            kw['date_order_local']=self._sales_date_local(kw['order'].date_order)
            kw['line_boot_json'] = json.dumps(self._line_boot(kw['order']))
            kw.update(kw['order']._absar_review_permissions(request.env.user))
        return request.render(template, kw)

    def _list_view(self, *, monitor=False, queue=False, updates=False, params=None):
        user = self._allowed(approve=True) if queue else self._allowed(view=True)
        is_approver = user.has_group('absar_portal_sales.group_portal_sales_approver')
        is_monitor = user.has_group('absar_portal_sales.group_portal_sales_monitor')
        if monitor and not is_monitor:
            raise Forbidden()
        params = params or {}
        domain = [('company_id', 'in', user.company_ids.ids)]
        if queue:
            domain += [('absar_portal_creator_id','!=',False), ('absar_portal_creator_id','!=',user.id),
                       ('absar_portal_submitter_id','!=',user.id),('absar_order_requester_id','!=',user.id),
                       '|',('absar_portal_review_state','=','submitted'),('absar_order_review_state','=','requested'), ('state','in',['draft','sent'])]
        elif updates:
            domain += [('absar_sales_decision_at','!=',False),'|','|',
                ('absar_portal_creator_id','=',user.id),('absar_portal_submitter_id','=',user.id),('absar_order_requester_id','=',user.id)]
        elif not monitor and not self._operator():
            domain += [('absar_portal_creator_id','=',user.id)]
        else:
            source = params.get('source', 'all')
            if source == 'portal':
                domain += [('absar_portal_creator_id','!=',False)]
            elif source == 'backend':
                domain += [('absar_portal_creator_id','=',False)]
            state = params.get('sales_state', 'all')
            if state == 'quotation':
                domain += [('state','in',['draft','sent'])]
            elif state == 'order':
                domain += [('state','in',['sale','done'])]
            elif state == 'cancel':
                domain += [('state','=','cancel')]
            review = params.get('review', 'all')
            if review in ('draft','submitted','approved','returned'):
                domain += [('absar_portal_creator_id','!=',False),('absar_portal_review_state','=',review)]
            elif review == 'na':
                domain += [('absar_portal_creator_id','=',False)]
        query = (params.get('q') or '').strip()[:120]
        if query:
            domain = expression.AND([domain, ['|','|','|',
                ('name','ilike',query),('partner_id.name','ilike',query),
                ('construction_project_id.name','ilike',query),('user_id.name','ilike',query)]])
        model = request.env['sale.order'].sudo()
        count = model.search_count(domain)
        per_page = 20
        try:
            page = max(1, min(int(params.get('page') or 1), max(1, (count + per_page - 1) // per_page)))
        except (ValueError,TypeError):
            page = 1
        orders = model.search(domain, limit=per_page, offset=(page-1)*per_page, order='absar_sales_decision_at desc, id desc' if updates else 'date_order desc, id desc')
        pending_count = model.search_count([('company_id','in',user.company_ids.ids),
                ('absar_portal_creator_id','!=',False),('absar_portal_creator_id','!=',user.id),
                ('absar_portal_submitter_id','!=',user.id),('absar_order_requester_id','!=',user.id),
                '|',('absar_portal_review_state','=','submitted'),('absar_order_review_state','=','requested'),('state','in',['draft','sent'])]) if is_approver else 0
        if queue or updates:
            request.env['portal.report.seen'].sudo()._mark_seen(user.id,'sales_approval' if queue else 'sales_review_update')
        base_url = BASE + ('/approvals' if queue else '/updates' if updates else '/monitor' if monitor else '')
        def page_url(target):
            args = {k:params.get(k) for k in ('q','source','sales_state','review') if params.get(k) and params.get(k) != 'all'}
            args['page'] = target
            return base_url + '?' + urlencode(args)
        return self._render('absar_portal_sales.sales_list', orders=orders,
            is_approver=is_approver, can_create=user.has_group('absar_portal_sales.group_portal_sales_creator'),
            is_monitor=is_monitor, monitoring=monitor, queue_only=queue, updates_only=updates, pending_count=pending_count,
            page=page, pages=max(1,(count+per_page-1)//per_page), total_count=count,
            previous_url=page_url(page-1), next_url=page_url(page+1), q=query,
            source=params.get('source','all'), sales_state=params.get('sales_state','all'),review=params.get('review','all'))

    @http.route(BASE+'/search-more',type='http',auth='user',methods=['POST'],csrf=True)
    def search_more(self,**post):
        self._allowed()
        data=json.loads(post.get('payload') or '{}');kind=data.get('kind');q=str(data.get('q') or '')[:120]
        allowed=[('active','=',True),'|',('company_id','=',False),('company_id','in',request.env.user.company_ids.ids)]
        if kind=='partner_id':model='res.partner';domain=allowed+[('absar_is_sales_customer','=',True)]
        elif kind=='project_id':
            partner=request.env['res.partner'].sudo().browse(int(data.get('partner_id') or 0)).exists()
            if not partner or partner not in self._partners(limit=None):raise Forbidden()
            model='project.project';domain=allowed+[('partner_id.commercial_partner_id','=',partner.commercial_partner_id.id)]
        elif kind=='uom_id':model='uom.uom';domain=[('active','=',True)]
        elif kind=='template_id':model='absar.proposal.template';domain=allowed
        else:raise Forbidden()
        if q:domain=expression.AND([domain,[('name','ilike',q)]])
        offset=max(0,min(int(data.get('offset') or 0),100000))
        records=request.env[model].sudo().search(domain,order='name,id',offset=offset,limit=31)
        return request.make_json_response({'items':[{'id':r.id,'name':r.display_name,
            'customer_id':r.commercial_partner_id.id if kind=='partner_id' else r.partner_id.commercial_partner_id.id if kind=='project_id' else 0} for r in records[:30]],'more':len(records)>30})

    @http.route(BASE, type='http', auth='user', website=True)
    def list_orders(self, **kw):
        user = request.env.user
        can_prepare = user.has_group('absar_portal_sales.group_portal_sales_creator')
        can_monitor = user.has_group('absar_portal_sales.group_portal_sales_monitor')
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
        return self._render('absar_portal_sales.sales_new',date_order_local=self._sales_date_local(fields.Datetime.now()),line_boot_json=json.dumps(self._line_boot(order)),partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units())

    @http.route(BASE + '/create', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def create_order(self, **post):
        user = self._allowed()
        try:
            partner = request.env['res.partner'].sudo().browse(int(post.get('partner_id') or 0)).exists()
            if not partner or partner not in self._partners(limit=None):
                raise UserError(_('Select an available customer.'))
            kind = post.get('kind')
            if kind not in ('standard','technical'):
                raise UserError(_('Invalid document type.'))
            project_id = int(post.get('project_id') or 0)
            project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
            if project_id and (not project or project not in self._customer_projects(partner)):
                raise UserError(_('Select an available project.'))
            vals = {
                'partner_id':partner.id, 'company_id':user.company_id.id, 'user_id':user.id,
                'absar_proposal_type':kind, 'absar_portal_creator_id':user.id,
                'absar_portal_review_state':'draft', 'construction_project_id':project.id if project else False,
            }
            if post.get('validity_date'):
                vals['validity_date'] = fields.Date.to_date(post['validity_date'])
            if kind == 'technical' and post.get('template_id'):
                template = request.env['absar.proposal.template'].sudo().browse(int(post['template_id'])).exists()
                if not template or template not in self._templates():
                    raise UserError(_('Invalid proposal template.'))
                vals['absar_proposal_template_id'] = template.id
            order = request.env['sale.order'].sudo().with_company(user.company_id).create(vals)
            if vals.get('absar_proposal_template_id'):
                order.action_absar_load_proposal_template()
            return request.redirect('%s/%s' % (BASE, order.id))
        except (ValueError, TypeError, UserError, ValidationError) as exc:
            return self._render('absar_portal_sales.sales_new',date_order_local=self._sales_date_local(fields.Datetime.now()),line_boot_json=json.dumps(self._line_boot(self._line_new_order({})[0])),partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units(),error=str(exc))

    @http.route(BASE + '/<int:order_id>', type='http', auth='user', website=True)
    def show_order(self, order_id, **kw):
        order = self._order(order_id)
        can_edit=False
        try:self._editable(order);can_edit=True
        except Forbidden:pass
        return self._render('absar_portal_sales.sales_detail', order=order, can_confirm=order._absar_portal_can_confirm(request.env.user),
            can_edit=can_edit,
            can_review=(request.env.user.has_group('absar_portal_sales.group_portal_sales_approver') and order.absar_portal_review_state=='submitted' and request.env.user not in (order.absar_portal_creator_id,order.absar_portal_submitter_id)),
            templates=self._templates(),projects=self._customer_projects(order.partner_id),units=self._units())

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
        vals={'absar_proposal_reference':False, 'user_id':(order.user_id or order.absar_portal_creator_id or request.env.user).id}
        project_id = int(post.get('project_id') or 0)
        project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
        if project_id and (not project or project not in self._customer_projects(order.partner_id)):
            raise Forbidden()
        vals['construction_project_id'] = project.id if project else False
        if order.absar_proposal_type=='technical':
            vals['absar_proposal_title']=(post.get('title') or 'Technical & Financial Proposal')[:160]
        try:
            vals['date_order']=self._sales_date_utc(post.get('date_order'))
            vals['validity_date']=fields.Date.to_date(post['validity_date']) if post.get('validity_date') else False
            order.sudo().write(vals)
        except (ValueError,ValidationError) as exc:
            return self._render('absar_portal_sales.sales_detail',order=order,can_edit=True,can_review=False,error=str(exc),templates=self._templates(),projects=self._customer_projects(order.partner_id),units=self._units())
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

    @http.route(BASE + '/<int:order_id>/template', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def load_template(self,order_id,**post):
        order=self._order(order_id); self._editable(order)
        if order.absar_proposal_type!='technical': raise Forbidden()
        template=request.env['absar.proposal.template'].sudo().browse(int(post.get('template_id') or 0)).exists()
        if not template or template not in self._templates(): raise Forbidden()
        order.sudo().write({'absar_proposal_template_id':template.id})
        order.sudo().action_absar_load_proposal_template()
        return request.redirect('%s/%s' % (BASE,order.id))

    def _place_section(self, order, section, raw_position):
        """Insert a section at the requested 1-based position, shifting others."""
        sections = list(order.absar_proposal_section_ids.sorted(key=lambda s: (s.sequence, s.id)))
        if section not in sections:
            raise Forbidden()
        sections.remove(section)
        try:
            position = int(raw_position)
        except (TypeError, ValueError):
            raise Forbidden()
        if position < 1 or position > len(sections) + 1:
            raise Forbidden()
        sections.insert(position - 1, section)
        for index, item in enumerate(sections, 1):
            if item.sequence != index * 10:
                item.sudo().write({'sequence': index * 10})

    @http.route(BASE + '/<int:order_id>/section/add', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_section(self,order_id,**post):
        order=self._order(order_id); self._editable(order)
        if order.absar_proposal_type!='technical': raise Forbidden()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        section_type=post.get('section_type') or 'custom'
        allowed=dict(request.env['absar.proposal.section']._fields['section_type'].selection)
        if section_type not in allowed: raise Forbidden()
        section = request.env['absar.proposal.section'].sudo().create({'order_id':order.id,'name':name,'section_type':section_type,'content':post.get('content') or '', 'page_break_before':post.get('page_break')=='1','sequence':max(order.absar_proposal_section_ids.mapped('sequence') or [0])+10})
        self._place_section(order, section, post.get('position') or len(order.absar_proposal_section_ids))
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def save_section(self,order_id,section_id,**post):
        order=self._order(order_id); self._editable(order)
        section=order.absar_proposal_section_ids.filtered(lambda s:s.id==section_id)
        if not section: raise NotFound()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        section_type=post.get('section_type') or section.section_type
        if section_type not in dict(section._fields['section_type'].selection): raise Forbidden()
        section.sudo().write({'name':name,'section_type':section_type,'content':post.get('content') or '', 'include_in_report':post.get('include')=='1','page_break_before':post.get('page_break')=='1'})
        self._place_section(order, section, post.get('position'))
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/move', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def move_section(self,order_id,section_id,**post):
        order=self._order(order_id); self._editable(order)
        sections=order.absar_proposal_section_ids.sorted(key=lambda x:(x.sequence,x.id))
        section=sections.filtered(lambda x:x.id==section_id)
        if not section: raise NotFound()
        values=list(sections)
        idx=values.index(section)
        other=idx+(-1 if post.get('direction')=='up' else 1)
        if 0<=other<len(values):
            values[idx],values[other]=values[other],values[idx]
            for i,item in enumerate(values): item.sudo().write({'sequence':(i+1)*10})
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/sections/reorder', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def reorder_sections(self, order_id, **post):
        order = self._order(order_id)
        self._editable(order)
        try:
            incoming = [int(value) for value in (post.get('section_ids') or '').split(',') if value.strip()]
        except ValueError:
            raise Forbidden()
        existing = order.absar_proposal_section_ids.ids
        if len(incoming) != len(existing) or len(set(incoming)) != len(existing) or set(incoming) != set(existing):
            raise Forbidden()
        for index, section_id in enumerate(incoming, start=1):
            order.absar_proposal_section_ids.filtered(lambda x: x.id == section_id).sudo().write({'sequence': index * 10})
        return request.redirect('%s/%s' % (BASE, order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def delete_section(self,order_id,section_id,**post):
        order=self._order(order_id); self._editable(order)
        section=order.absar_proposal_section_ids.filtered(lambda s:s.id==section_id)
        if not section: raise NotFound()
        section.sudo().unlink()
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/milestone/add', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_milestone(self,order_id,**post):
        order=self._order(order_id); self._editable(order)
        if order.absar_proposal_type!='technical': raise Forbidden()
        rate=self._num(post.get('percentage'),'Percentage')
        if rate>100: raise Forbidden()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        request.env['absar.proposal.payment'].sudo().create({'order_id':order.id,'name':name,'percentage':rate,'due_condition':(post.get('due_condition') or '')[:255]})
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/milestone/<int:milestone_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def delete_milestone(self,order_id,milestone_id,**post):
        order=self._order(order_id); self._editable(order)
        milestone=order.absar_proposal_payment_ids.filtered(lambda p:p.id==milestone_id)
        if not milestone: raise NotFound()
        milestone.sudo().unlink()
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/workflow', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def workflow(self,order_id,**post):
        order=self._order(order_id)
        action=post.get('action')
        if action=='request_order':
            order.action_absar_request_order()
        elif action=='submit':
            self._editable(order)
            order._absar_portal_submit()
            return request.redirect(BASE)
        elif action in ('approve','return','approve_order','return_order'):
            self._allowed(approve=True)
            if action=='approve':order.action_absar_portal_approve()
            elif action=='approve_order':order.action_absar_approve_order()
            else:
                note=(post.get('note') or '').strip()
                if not note:raise Forbidden()
                order.sudo().write({'absar_portal_review_note':note[:3000]})
                if action=='return_order':order.action_absar_return_order()
                else:order.action_absar_portal_return()
        else: raise Forbidden()
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/pdf', type='http', auth='user', website=True)
    def pdf(self,order_id,**kw):
        order=self._order(order_id)
        if order.state in ('draft','sent') and (order.absar_portal_review_state!='approved' or not order.absar_portal_approver_id): raise Forbidden()
        report='absar_technical_proposal.report_technical_proposal' if order.absar_proposal_type=='technical' else 'sale.report_saleorder'
        content,_=request.env['ir.actions.report'].sudo()._render_qweb_pdf(report,[order.id])
        return request.make_response(content,headers=[('Content-Type','application/pdf'),('Content-Disposition','inline; filename="%s.pdf"' % order.name.replace('/','-'))])
