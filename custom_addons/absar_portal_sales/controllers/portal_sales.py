from werkzeug.exceptions import Forbidden, NotFound
from odoo import http, fields, _
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.tools import float_compare

BASE = '/my/employee/sales'

class PortalSales(http.Controller):
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
        if not order or not order.absar_portal_creator_id or order.company_id not in user.company_ids:
            raise NotFound()
        if not review and order.absar_portal_creator_id.id != user.id and not user.has_group('absar_portal_sales.group_portal_sales_approver') and not (user.has_group('absar_portal_sales.group_portal_sales_monitor') and order.absar_portal_review_state in ('submitted','approved','returned')):
            raise NotFound()
        return order

    def _editable(self, order):
        if order.absar_portal_creator_id.id != request.env.user.id or order.absar_portal_review_state not in ('draft','returned') or order.state != 'draft':
            raise Forbidden()

    def _num(self, value, field='Amount'):
        try:
            result = float(value or 0)
        except (ValueError, TypeError):
            raise UserError(_('%s must be a number.') % field)
        if result < 0 or result != result or result == float('inf'):
            raise UserError(_('%s must be a nonnegative finite number.') % field)
        return result

    def _partners(self):
        return request.env['res.partner'].sudo().search([
            ('customer_rank','>',0), ('active','=',True),
            '|', ('company_id','=',False), ('company_id','in',request.env.user.company_ids.ids)
        ], limit=500, order='name')

    def _projects(self):
        return request.env['project.project'].sudo().search([
            ('active','=',True), '|', ('company_id','=',False),
            ('company_id','in',request.env.user.company_ids.ids)
        ], limit=500, order='name')

    def _units(self):
        return request.env['uom.uom'].sudo().search([('active','=',True)],order='name',limit=400)

    def _templates(self):
        return request.env['absar.proposal.template'].sudo().search([
            ('active','=',True), '|', ('company_id','=',False), ('company_id','in',request.env.user.company_ids.ids)
        ], order='name')

    def _render(self, template, **kw):
        kw.setdefault('error', False)
        return request.render(template, kw)

    @http.route(BASE, type='http', auth='user', website=True)
    def list_orders(self, **kw):
        user = self._allowed(view=True)
        is_monitor = user.has_group('absar_portal_sales.group_portal_sales_monitor')
        is_approver = user.has_group('absar_portal_sales.group_portal_sales_approver')
        domain = [('absar_portal_creator_id','!=',False),('company_id','in',user.company_ids.ids)]
        if not is_approver:
            if is_monitor:
                domain += [('absar_portal_review_state','in',('submitted','approved','returned'))]
            else:
                domain += [('absar_portal_creator_id','=',user.id)]
        orders = request.env['sale.order'].sudo().search(domain, limit=100, order='id desc')
        return self._render('absar_portal_sales.sales_list', orders=orders, is_approver=is_approver, can_create=user.has_group('absar_portal_sales.group_portal_sales_creator'), pending_count=len(orders.filtered(lambda o:o.absar_portal_review_state=='submitted')))

    @http.route(BASE + '/approvals', type='http', auth='user', website=True)
    def approval_queue(self, **kw):
        user=self._allowed(approve=True)
        orders=request.env['sale.order'].sudo().search([('absar_portal_review_state','=','submitted'),('absar_portal_creator_id','!=',user.id),('company_id','in',user.company_ids.ids),('state','=','draft')],order='write_date desc',limit=100)
        return self._render('absar_portal_sales.sales_list',orders=orders,is_approver=True,can_create=True,pending_count=len(orders),queue_only=True)

    @http.route(BASE + '/new', type='http', auth='user', website=True)
    def new_order(self, **kw):
        self._allowed()
        return self._render('absar_portal_sales.sales_new', partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units())

    @http.route(BASE + '/create', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def create_order(self, **post):
        user = self._allowed()
        try:
            partner = request.env['res.partner'].sudo().browse(int(post.get('partner_id') or 0)).exists()
            if not partner or partner not in self._partners():
                raise UserError(_('Select an available customer.'))
            kind = post.get('kind')
            if kind not in ('standard','technical'):
                raise UserError(_('Invalid document type.'))
            project_id = int(post.get('project_id') or 0)
            project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
            if project_id and (not project or project not in self._projects()):
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
            return self._render('absar_portal_sales.sales_new',partners=self._partners(),projects=self._projects(),templates=self._templates(),units=self._units(),error=str(exc))

    @http.route(BASE + '/<int:order_id>', type='http', auth='user', website=True)
    def show_order(self, order_id, **kw):
        order = self._order(order_id)
        return self._render('absar_portal_sales.sales_detail', order=order,
            can_edit=(request.env.user.has_group('absar_portal_sales.group_portal_sales_creator') and order.absar_portal_creator_id.id == request.env.user.id and order.absar_portal_review_state in ('draft','returned') and order.state=='draft'),
            can_review=(request.env.user.has_group('absar_portal_sales.group_portal_sales_approver') and order.absar_portal_review_state=='submitted' and order.absar_portal_creator_id.id != request.env.user.id),
            templates=self._templates(),projects=self._projects(),units=self._units())

    @http.route(BASE + '/<int:order_id>/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def save_order(self, order_id, **post):
        order=self._order(order_id); self._editable(order)
        vals={'absar_proposal_reference':False, 'user_id':order.absar_portal_creator_id.id}
        project_id = int(post.get('project_id') or 0)
        project = request.env['project.project'].sudo().browse(project_id).exists() if project_id else False
        if project_id and (not project or project not in self._projects()):
            raise Forbidden()
        vals['construction_project_id'] = project.id if project else False
        if order.absar_proposal_type=='technical':
            vals['absar_proposal_title']=(post.get('title') or 'Technical & Financial Proposal')[:160]
        try:
            vals['validity_date']=fields.Date.to_date(post['validity_date']) if post.get('validity_date') else False
            order.sudo().write(vals)
        except (ValueError,ValidationError) as exc:
            return self._render('absar_portal_sales.sales_detail',order=order,can_edit=True,can_review=False,error=str(exc),templates=self._templates(),projects=self._projects(),units=self._units())
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
            return request.redirect('%s/%s?error=add_line' % (BASE,order.id))
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
        if action=='submit':
            self._editable(order)
            if not order.order_line: raise Forbidden()
            if order.absar_proposal_type=='technical' and order.absar_proposal_payment_ids:
                total=sum(order.absar_proposal_payment_ids.mapped('percentage'))
                if float_compare(total,100,precision_digits=2): raise Forbidden()
            order.sudo().write({'absar_portal_review_state':'submitted','absar_portal_review_note':False})
            order._absar_portal_notify_reviewers()
        elif action in ('approve','return'):
            self._allowed(approve=True)
            if order.absar_portal_review_state!='submitted' or order.state!='draft': raise Forbidden()
            if order.absar_portal_creator_id.id == request.env.user.id: raise Forbidden()
            if action=='approve' and order.absar_portal_creator_id.id == request.env.user.id: raise Forbidden()
            if action=='approve':
                order.sudo().write({'absar_portal_review_state':'approved','absar_portal_approver_id':request.env.user.id})
                order._absar_portal_notify_creator(_('Your quotation %s has been approved for sending.') % order.name)
            else:
                note=(post.get('note') or '').strip()
                if not note: raise Forbidden()
                order.sudo().write({'absar_portal_review_state':'returned','absar_portal_review_note':note[:3000]})
                order._absar_portal_notify_creator(_('Your quotation %s was returned for correction: %s') % (order.name,note[:500]))
        else: raise Forbidden()
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/pdf', type='http', auth='user', website=True)
    def pdf(self,order_id,**kw):
        order=self._order(order_id)
        if order.absar_portal_review_state!='approved': raise Forbidden()
        report='absar_technical_proposal.report_technical_proposal' if order.absar_proposal_type=='technical' else 'sale.report_saleorder'
        content,_=request.env['ir.actions.report'].sudo()._render_qweb_pdf(report,[order.id])
        return request.make_response(content,headers=[('Content-Type','application/pdf'),('Content-Disposition','inline; filename="%s.pdf"' % order.name.replace('/','-'))])
