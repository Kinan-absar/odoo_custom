"""Original technical proposal controls in the existing optional EPS bridge."""
import json
from odoo import http, Command, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare
from werkzeug.exceptions import Forbidden, NotFound
from odoo.addons.portal_backend_workspace.controllers.sales.portal_sales import PortalSales, BASE


class WorkspaceSalesProposals(PortalSales):
    def _templates(self, company=None):
        if not request.env['sale.order']._pbw_has_technical_proposals():
            return []
        companies = company or request.env.user.company_ids
        if any(c not in request.env.user.company_ids for c in companies):
            raise Forbidden()
        return request.env['absar.proposal.template'].sudo().search([
            ('active', '=', True), '|', ('company_id', '=', False),
            ('company_id', 'in', companies.ids)], order='name,id')

    def _render(self, template, **kw):
        if kw.get('order'):
            kw['templates'] = self._templates(kw['order'].company_id)
        return super()._render(template, **kw)

    def _proposal_order(self, order_id, write=False):
        order = self._order(order_id)
        if not order._pbw_has_technical_proposals() or order._pbw_sales_document_type() != 'technical':
            raise NotFound()
        if write:
            self._editable(order)
            # Recheck after taking the same parent lock used by submission.
            order._pbw_portal_lock()
            self._editable(order)
            if request.httprequest.content_length and request.httprequest.content_length > 2_000_000:
                raise ValidationError(_('Request is too large.'))
        return order

    @http.route()
    def search_more(self, **post):
        self._allowed()
        try:
            data = json.loads(post.get('payload') or '{}')
        except (ValueError, TypeError):
            raise Forbidden()
        if not isinstance(data, dict):
            raise Forbidden()
        if data.get('kind') != 'template_id':
            return super().search_more(**post)
        if not request.env['sale.order']._pbw_has_technical_proposals():
            raise Forbidden()
        if data.get('order_id'):
            order = self._order(self._line_id(data['order_id']))
            company = order.company_id
        else:
            partner = False
            if data.get('partner_id'):
                partner = request.env['res.partner'].sudo().browse(self._line_id(data['partner_id'])).exists()
                if not partner or partner not in self._partners(limit=None):
                    raise Forbidden()
            company = self._sales_company(partner)
        query = str(data.get('q') or '')[:120]
        domain = [('active','=',True), '|', ('company_id','=',False), ('company_id','=',company.id)]
        if query:
            domain.append(('name','ilike',query))
        try:
            offset = max(0, min(int(data.get('offset') or 0), 100000))
        except (ValueError,TypeError,OverflowError):
            raise Forbidden()
        records = request.env['absar.proposal.template'].sudo().search(domain, order='name,id', offset=offset, limit=31)
        return request.make_json_response({'items':[{'id':r.id,'name':r.display_name} for r in records[:30]], 'more':len(records)>30})

    @http.route()
    def pdf(self, order_id, **kw):
        order = self._order(order_id)
        if order._pbw_sales_document_type() != 'technical':
            return super().pdf(order_id, **kw)
        if not order._pbw_can_print_for(request.env.user):
            raise Forbidden()
        if not order._pbw_has_technical_proposals():
            raise NotFound()
        if order.absar_proposal_payment_ids:
            total = sum(order.absar_proposal_payment_ids.mapped('percentage'))
            if float_compare(total, 100.0, precision_digits=2) != 0:
                raise UserError(_('Payment milestones must total 100%% before printing (currently %.2f%%).') % total)
        report_xmlid = 'absar_technical_proposal.action_report_absar_technical_proposal'
        report = request.env.ref(report_xmlid, raise_if_not_found=False)
        if not report or report.sudo().model != 'sale.order' or report.sudo().report_type != 'qweb-pdf':
            raise UserError(_('The installed technical proposal PDF report is unavailable.'))
        content, _kind = request.env['ir.actions.report'].sudo().with_company(order.company_id)._render_qweb_pdf(report_xmlid,[order.id])
        filename = str(order.name or 'Proposal').replace('/', '-').replace('"', '').replace('\r','').replace('\n','')
        return request.make_response(content, headers=[('Content-Type','application/pdf'), ('Content-Disposition','inline; filename="%s.pdf"' % filename)])

    @http.route(BASE + '/<int:order_id>/template', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def load_template(self,order_id,**post):
        order=self._proposal_order(order_id, write=True)
        if order.absar_proposal_type!='technical': raise Forbidden()
        template=order._pbw_proposal_template(post.get('template_id'), order.company_id)
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
                order.write({'absar_proposal_section_ids': [Command.update(item.id, {'sequence': index * 10})]})

    @http.route(BASE + '/<int:order_id>/section/add', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_section(self,order_id,**post):
        order=self._proposal_order(order_id, write=True)
        if order.absar_proposal_type!='technical': raise Forbidden()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        section_type=post.get('section_type') or 'custom'
        allowed=dict(request.env['absar.proposal.section']._fields['section_type'].selection)
        if section_type not in allowed: raise Forbidden()
        existing = set(order.absar_proposal_section_ids.ids)
        order.write({'absar_proposal_section_ids': [Command.create({'name':name,'section_type':section_type,'content':post.get('content') or '', 'page_break_before':post.get('page_break')=='1','sequence':max(order.absar_proposal_section_ids.mapped('sequence') or [0])+10})]})
        section = order.absar_proposal_section_ids.filtered(lambda s:s.id not in existing)
        self._place_section(order, section, post.get('position') or len(order.absar_proposal_section_ids))
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/save', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def save_section(self,order_id,section_id,**post):
        order=self._proposal_order(order_id, write=True)
        section=order.absar_proposal_section_ids.filtered(lambda s:s.id==section_id)
        if not section: raise NotFound()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        section_type=post.get('section_type') or section.section_type
        if section_type not in dict(section._fields['section_type'].selection): raise Forbidden()
        order.write({'absar_proposal_section_ids': [Command.update(section.id, {'name':name,'section_type':section_type,'content':post.get('content') or '', 'include_in_report':post.get('include')=='1','page_break_before':post.get('page_break')=='1'})]})
        self._place_section(order, section, post.get('position'))
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/move', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def move_section(self,order_id,section_id,**post):
        order=self._proposal_order(order_id, write=True)
        sections=order.absar_proposal_section_ids.sorted(key=lambda x:(x.sequence,x.id))
        section=sections.filtered(lambda x:x.id==section_id)
        if not section: raise NotFound()
        values=list(sections)
        idx=values.index(section)
        other=idx+(-1 if post.get('direction')=='up' else 1)
        if 0<=other<len(values):
            values[idx],values[other]=values[other],values[idx]
            for i,item in enumerate(values): order.write({'absar_proposal_section_ids': [Command.update(item.id, {'sequence':(i+1)*10})]})
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/sections/reorder', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def reorder_sections(self, order_id, **post):
        order = self._proposal_order(order_id, write=True)
        try:
            incoming = [int(value) for value in (post.get('section_ids') or '').split(',') if value.strip()]
        except ValueError:
            raise Forbidden()
        existing = order.absar_proposal_section_ids.ids
        if len(incoming) != len(existing) or len(set(incoming)) != len(existing) or set(incoming) != set(existing):
            raise Forbidden()
        for index, section_id in enumerate(incoming, start=1):
            order.write({'absar_proposal_section_ids': [Command.update(section_id, {'sequence': index * 10})]})
        return request.redirect('%s/%s' % (BASE, order.id))

    @http.route(BASE + '/<int:order_id>/section/<int:section_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def delete_section(self,order_id,section_id,**post):
        order=self._proposal_order(order_id, write=True)
        section=order.absar_proposal_section_ids.filtered(lambda s:s.id==section_id)
        if not section: raise NotFound()
        order.write({'absar_proposal_section_ids': [Command.delete(section.id)]})
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/milestone/add', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def add_milestone(self,order_id,**post):
        order=self._proposal_order(order_id, write=True)
        if order.absar_proposal_type!='technical': raise Forbidden()
        rate=self._num(post.get('percentage'),'Percentage')
        if rate>100: raise Forbidden()
        name=(post.get('name') or '').strip()
        if not name or len(name)>180: raise Forbidden()
        order.write({'absar_proposal_payment_ids': [Command.create({'name':name,'percentage':rate,'due_condition':(post.get('due_condition') or '')[:255]})]})
        return request.redirect('%s/%s' % (BASE,order.id))

    @http.route(BASE + '/<int:order_id>/milestone/<int:milestone_id>/delete', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def delete_milestone(self,order_id,milestone_id,**post):
        order=self._proposal_order(order_id, write=True)
        milestone=order.absar_proposal_payment_ids.filtered(lambda p:p.id==milestone_id)
        if not milestone: raise NotFound()
        order.write({'absar_proposal_payment_ids': [Command.delete(milestone.id)]})
        return request.redirect('%s/%s' % (BASE,order.id))

