"""Optional adapter for the original installed proposal engine, not a copy.

No foreign models are inherited and no foreign field is defined by this addon.
Every entry point checks the known model/field contract before reading it.
"""
import json
import math
from odoo import api, models, Command, _
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
    def _pbw_proposal_header_map(self):
        names = {
            'title': 'absar_proposal_title',
            'reference': 'absar_proposal_reference',
            'signatory': 'absar_proposal_signatory',
            'signatory_title': 'absar_proposal_signatory_title',
            'customer_signatory': 'absar_proposal_customer_signatory',
            'customer_signatory_title': 'absar_proposal_customer_signatory_title',
        }
        return {key: name for key, name in names.items()
                if name in self._fields and self._fields[name].type == 'char'}

    @api.model
    def _pbw_proposal_header_values(self, header):
        values = {}
        for key, name in self._pbw_proposal_header_map().items():
            if key in header:
                value = header[key]
                if value is not None and not isinstance(value, str):
                    raise ValidationError(_('Invalid proposal header.'))
                value = (value or '').strip()
                if key == 'title':
                    value = value or 'TECHNICAL & FINANCIAL PROPOSAL'
                values[name] = value[:160] or False
        return values

    @api.model
    def _pbw_proposal_section_types(self):
        if not self._pbw_has_technical_proposals():
            return []
        field = self.env['absar.proposal.section']._fields['section_type']
        return field._description_selection(self.env)

    @api.model
    def _pbw_proposal_default_section(self, kind):
        """Run the installed engine's onchange on a virtual record; no DB write."""
        if kind not in dict(self._pbw_proposal_section_types()):
            raise ValidationError(_('Choose an available section type.'))
        section = self.env['absar.proposal.section'].sudo().new({'section_type': kind})
        onchange = getattr(section, '_onchange_section_type_name', None)
        if callable(onchange):
            onchange()
        return {'section_type': kind, 'name': section.name or dict(self._pbw_proposal_section_types())[kind],
                'content': section.content or '', 'include_in_report': True,
                'page_break_before': bool(section.page_break_before)}

    @api.model
    def _pbw_proposal_draft_values(self, raw):
        """Accept new children only; no model/field names or child IDs from clients."""
        if not isinstance(raw, str) or len(raw) > 1_000_000:
            raise ValidationError(_('Invalid or oversized proposal content.'))
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            raise ValidationError(_('Invalid proposal content.'))
        if not isinstance(data, dict) or set(data) - {'sections', 'payments'}:
            raise ValidationError(_('Invalid proposal content.'))
        sections = data.get('sections', [])
        payments = data.get('payments', [])
        if not isinstance(sections, list) or len(sections) > 100:
            raise ValidationError(_('Use at most 100 technical sections.'))
        if not isinstance(payments, list) or len(payments) > 50:
            raise ValidationError(_('Use at most 50 payment milestones.'))
        allowed_types = dict(self._pbw_proposal_section_types())
        commands = []
        for index, row in enumerate(sections, 1):
            if not isinstance(row, dict) or set(row) - {'name', 'section_type', 'content', 'include_in_report', 'page_break_before'}:
                raise ValidationError(_('Invalid technical section.'))
            name = row.get('name')
            content = row.get('content', '')
            kind = row.get('section_type')
            if not isinstance(name, str) or not name.strip() or len(name) > 180 or kind not in allowed_types:
                raise ValidationError(_('Set a valid section title and type.'))
            if not isinstance(content, str) or len(content) > 200_000:
                raise ValidationError(_('Technical section content is too large.'))
            for key in ('include_in_report', 'page_break_before'):
                if key in row and not isinstance(row[key], bool):
                    raise ValidationError(_('Invalid section option.'))
            commands.append(Command.create({'name': name.strip(), 'section_type': kind,
                'content': content, 'sequence': index * 10,
                'include_in_report': row.get('include_in_report', True),
                'page_break_before': row.get('page_break_before', False)}))
        payment_commands = []
        for index, row in enumerate(payments, 1):
            if not isinstance(row, dict) or set(row) - {'name', 'percentage', 'due_condition'}:
                raise ValidationError(_('Invalid payment milestone.'))
            name = row.get('name'); due = row.get('due_condition', '')
            try:
                if isinstance(row.get('percentage'), bool):
                    raise ValueError()
                rate = float(row.get('percentage', 0))
            except (ValueError, TypeError, OverflowError):
                raise ValidationError(_('Set a valid milestone percentage.'))
            if not isinstance(name, str) or not name.strip() or len(name) > 180:
                raise ValidationError(_('Set a milestone name.'))
            if not isinstance(due, str) or len(due) > 255 or not math.isfinite(rate) or rate < 0 or rate > 100:
                raise ValidationError(_('Set a milestone percentage between 0 and 100 and a valid due condition.'))
            payment_commands.append(Command.create({'name': name.strip(), 'percentage': rate,
                'due_condition': due, 'sequence': index * 10}))
        return {'absar_proposal_section_ids': commands, 'absar_proposal_payment_ids': payment_commands}

    @api.model
    def _pbw_sales_document_values(self, kind, header=None, company=None):
        if not self._pbw_has_technical_proposals():
            return super()._pbw_sales_document_values(kind, header=header, company=company)
        if kind not in ('standard', 'technical'):
            raise ValidationError(_('This document type is not available.'))
        header = header or {}
        values = {'absar_proposal_type': kind}
        if kind == 'technical':
            values['absar_proposal_title'] = 'TECHNICAL & FINANCIAL PROPOSAL'
            values.update(self._pbw_proposal_header_values(header))
            if 'proposal_payload' in header:
                values.update(self._pbw_proposal_draft_values(header['proposal_payload']))
            if header.get('template_id'):
                values['absar_proposal_template_id'] = self._pbw_proposal_template(
                    header['template_id'], company).id
        elif header.get('template_id'):
            raise ValidationError(_('A proposal template requires Technical & Financial Proposal.'))
        return values

    def _pbw_sales_document_header_values(self, header):
        values = super()._pbw_sales_document_header_values(header)
        self.ensure_one()
        if self._pbw_sales_document_type() == 'technical':
            values.update(self._pbw_proposal_header_values(header))
        return values

    def _pbw_sales_after_document_create(self, header=None):
        result = super()._pbw_sales_after_document_create(header=header)
        for order in self:
            if (order._pbw_sales_document_type() == 'technical' and order.absar_proposal_template_id
                    and 'proposal_payload' not in (header or {})):
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
            fields.update(self._pbw_proposal_header_map().values())
            fields.update({'absar_proposal_type', 'absar_proposal_title',
                'absar_proposal_template_id', 'absar_proposal_section_ids',
                'absar_proposal_payment_ids'})
        return fields
