"""Enforce quotation approval for backend, portal and direct report requests."""
from copy import deepcopy
from lxml import etree
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderPrintApproval(models.Model):
    _inherit = 'sale.order'

    absar_can_print = fields.Boolean(compute='_compute_absar_can_print')

    @api.depends_context('uid')
    @api.depends('absar_portal_creator_id', 'absar_portal_review_state', 'absar_portal_approver_id')
    def _compute_absar_can_print(self):
        for order in self:
            required = order._absar_review_permissions(self.env.user.sudo(False))['requires_review']
            order.absar_can_print = not required or bool(
                order.absar_portal_review_state == 'approved' and order.absar_portal_approver_id)

    def _absar_assert_print_approved(self):
        for order in self:
            if not order.absar_can_print:
                raise UserError(_('Submit the quotation for approval and obtain approval before printing the quotation or pro-forma invoice.'))

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == 'form':
            arch = deepcopy(arch)
            header = arch.find('.//header')
            if header is not None:
                if not arch.xpath('.//field[@name="absar_can_print"]'):
                    etree.SubElement(header, 'field', name='absar_can_print', invisible='1')
                sale_reports=set(self.env['ir.actions.report'].sudo().search([('model','=','sale.order')]).ids)
                for button in header.findall('button'):
                    if (button.get('string', '').lower().startswith('print')
                            or (button.get('type')=='action' and button.get('name','').isdigit() and int(button.get('name')) in sale_reports)
                            or button.get('name') in ('print_quotation', 'action_quotation_print', 'action_print_quotation')):
                        old = button.get('invisible') or 'False'
                        button.set('invisible', '(%s) or not absar_can_print' % old)
        return arch, view


class SalesReportApproval(models.Model):
    _inherit = 'ir.actions.report'

    def _absar_check_sales_report(self, report_ref, res_ids, data=None):
        report = self._get_report(report_ref)
        if report.model == 'sale.order':
            ids = res_ids or (data or {}).get('ids') or self.env.context.get('active_ids') or []
            if isinstance(ids, int):
                ids = [ids]
            self.env['sale.order'].browse(ids).exists()._absar_assert_print_approved()

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        self._absar_check_sales_report(report_ref, res_ids, data)
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

    def _render_qweb_html(self, report_ref, docids, data=None):
        self._absar_check_sales_report(report_ref, docids, data)
        return super()._render_qweb_html(report_ref, docids, data=data)
