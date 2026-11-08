"""Optional adapter for the original installed proposal engine, not a copy.

No foreign models are inherited and no foreign field is defined by this addon.
Every entry point checks the known model/field contract before reading it.
"""
from odoo import api, models, _
from odoo.exceptions import ValidationError


class SalesProposalBridge(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _pbw_has_technical_proposals(self):
        expected = {
            'absar_proposal_type': ('selection', None),
            'absar_proposal_title': ('char', None),
            'absar_proposal_template_id': ('many2one', 'absar.proposal.template'),
            'absar_proposal_section_ids': ('one2many', 'absar.proposal.section'),
            'absar_proposal_payment_ids': ('one2many', 'absar.proposal.payment'),
        }
        for name, (kind, relation) in expected.items():
            field = self._fields.get(name)
            if field is None or field.type != kind:
                return False
            if relation and (field.comodel_name != relation or relation not in self.env):
                return False
        if not callable(getattr(self, 'action_absar_load_proposal_template', None)):
            return False
        values = dict(self._fields['absar_proposal_type']._description_selection(self.env))
        return 'standard' in values and 'technical' in values

    @api.model
    def _pbw_sales_document_types(self):
        types = list(super()._pbw_sales_document_types())
        if self._pbw_has_technical_proposals():
            types.append(('technical', _('Technical & Financial Proposal')))
        return types

    def _pbw_sales_document_type(self):
        self.ensure_one()
        if self._pbw_has_technical_proposals():
            return self.absar_proposal_type or 'standard'
        return super()._pbw_sales_document_type()

    @api.model
    def _pbw_proposal_template(self, ident, company):
        if not self._pbw_has_technical_proposals():
            raise ValidationError(_('The Technical & Financial Proposal engine is not installed.'))
        if not company or company not in self.env.user.sudo(False).company_ids:
            raise ValidationError(_('The proposal company is not available.'))
        if isinstance(ident, bool):
            raise ValidationError(_('Select an available proposal template.'))
        try:
            template_id = int(ident)
        except (ValueError, TypeError, OverflowError):
            raise ValidationError(_('Select an available proposal template.'))
        if template_id <= 0:
            raise ValidationError(_('Select an available proposal template.'))
        template = self.env['absar.proposal.template'].sudo().search([
            ('id', '=', template_id), ('active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ], limit=1)
        if not template:
            raise ValidationError(_('Select an active proposal template belonging to this company.'))
        return template

    @api.model
    def _pbw_sales_document_values(self, kind, header=None, company=None):
        if not self._pbw_has_technical_proposals():
            return super()._pbw_sales_document_values(kind, header=header, company=company)
        if kind not in ('standard', 'technical'):
            raise ValidationError(_('This document type is not available.'))
        header = header or {}
        values = {'absar_proposal_type': kind}
        if kind == 'technical':
            values['absar_proposal_title'] = str(header.get('title') or 'TECHNICAL & FINANCIAL PROPOSAL')[:160]
            if header.get('template_id'):
                values['absar_proposal_template_id'] = self._pbw_proposal_template(
                    header['template_id'], company).id
        elif header.get('template_id'):
            raise ValidationError(_('A proposal template requires Technical & Financial Proposal.'))
        return values

    def _pbw_sales_document_header_values(self, header):
        values = super()._pbw_sales_document_header_values(header)
        self.ensure_one()
        if self._pbw_sales_document_type() == 'technical' and 'title' in header:
            values['absar_proposal_title'] = str(header.get('title') or 'TECHNICAL & FINANCIAL PROPOSAL')[:160]
        return values

    def _pbw_sales_after_document_create(self):
        result = super()._pbw_sales_after_document_create()
        for order in self:
            if order._pbw_sales_document_type() == 'technical' and order.absar_proposal_template_id:
                order._pbw_proposal_template(order.absar_proposal_template_id.id, order.company_id)
                order.action_absar_load_proposal_template()
        return result

    def _pbw_sales_document_version(self):
        values = list(super()._pbw_sales_document_version())
        self.ensure_one()
        if self._pbw_has_technical_proposals():
            values.append([self.absar_proposal_type, self.absar_proposal_title,
                [(s.id, str(s.write_date)) for s in self.absar_proposal_section_ids.sorted('id')],
                [(p.id, str(p.write_date)) for p in self.absar_proposal_payment_ids.sorted('id')]])
        return values

    @api.model
    def _pbw_sales_extra_content_fields(self):
        fields = set(super()._pbw_sales_extra_content_fields())
        if self._pbw_has_technical_proposals():
            fields.update({'absar_proposal_type', 'absar_proposal_title',
                'absar_proposal_template_id', 'absar_proposal_section_ids',
                'absar_proposal_payment_ids'})
        return fields
