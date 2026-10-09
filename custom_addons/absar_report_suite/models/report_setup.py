"""Preserve existing report action IDs after declarative XML loading."""
import json
import logging
from pathlib import Path
from odoo import api, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)
_MODULE = 'absar_report_suite'
_BACKUP = _MODULE + '.original_report_actions'
_FIELDS = ['name', 'report_name', 'report_file', 'paperformat_id',
           'binding_model_id', 'binding_type', 'binding_view_types',
           'print_report_name', 'attachment_use']


class AbsarReportSetup(models.AbstractModel):
    _name = 'absar.report.setup'
    _description = 'ABSAR report action compatibility'

    @api.model
    def apply(self):
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError('Only Settings administrators can configure ABSAR reports.')
        env = self.env
        actions = env['ir.actions.report'].sudo()
        params = env['ir.config_parameter'].sudo()
        config = json.loads((Path(__file__).resolve().parents[1] / 'data/integration.json').read_text())
        backup = json.loads(params.get_param(_BACKUP, '{}'))
        owned = actions.browse([env.ref(_MODULE + '.' + r['alias']).id for r in config['reports']])
        bound = actions.browse()

        def remember(record):
            key = str(record.id)
            if key not in backup and record not in owned:
                values = record.read(_FIELDS)[0]
                values.pop('id', None)
                for field in ['paperformat_id', 'binding_model_id']:
                    values[field] = values[field][0] if values[field] else False
                backup[key] = values

        for item in config['reports']:
            canonical = env.ref(_MODULE + '.' + item['alias'])
            preferred = env.ref(item['xmlid'], raise_if_not_found=False) if item.get('xmlid') else False
            if preferred and (preferred._name != 'ir.actions.report' or preferred.model != item['model']):
                preferred = False
            candidates = actions.search([
                ('model', '=', item['model']), ('id', 'not in', owned.ids),
                '|', ('report_name', 'in', [item['legacy_report'], item['report_name']] + item.get('old_reports', [])),
                ('name', '=', item['name']),
            ], order='id')
            if preferred and preferred not in candidates:
                candidates |= preferred
            # Stable external IDs take precedence; duplicate display names cannot block install.
            saved_id = params.get_param(_MODULE + '.target.' + item['alias'])
            saved = actions.browse(int(saved_id)).exists() if saved_id and saved_id.isdigit() else False
            if saved and saved.model != item['model']:
                saved = False
            target = saved or preferred or candidates[:1] or canonical
            params.set_param(_MODULE + '.target.' + item['alias'], str(target.id))
            values = {field: canonical[field] for field in _FIELDS}
            for field in ['paperformat_id', 'binding_model_id']:
                values[field] = values[field].id or False
            values['binding_model_id'] = env['ir.model']._get(item['model']).id
            if target != canonical:
                remember(target)
                target.write(values)
                canonical.write({'binding_model_id': False})
            else:
                canonical.write({'binding_model_id': env['ir.model']._get(item['model']).id})
            bound |= target
            for duplicate in candidates - target:
                remember(duplicate)
                duplicate.write({'binding_model_id': False})

        # Keep standard internal invoice and sales buttons on the same designs.
        standard = {
            'account.account_invoices': 'invoice_payment_report',
            'account.account_invoices_without_payment': 'invoice_report',
            'sale.action_report_saleorder': 'quotation_report',
            'sale.action_report_pro_forma_invoice': 'proforma_report',
        }
        for xmlid, alias in standard.items():
            report = env.ref(xmlid, raise_if_not_found=False)
            if not report:
                continue
            canonical = env.ref(_MODULE + '.' + alias)
            remember(report)
            values = {'report_name': canonical.report_name, 'report_file': canonical.report_file,
                      'paperformat_id': canonical.paperformat_id.id, 'attachment_use': False}
            if report not in bound:
                values['binding_model_id'] = False
            report.write(values)

        retired = actions.search([('report_name', 'in', config['retired_templates']), ('id', 'not in', (owned | bound).ids)])
        for xmlid in config['retired_xmlids']:
            record = env.ref(xmlid, raise_if_not_found=False)
            if record and record._name == 'ir.actions.report' and record not in (owned | bound):
                retired |= record
        for record in retired:
            remember(record)
            record.write({'binding_model_id': False})
        params.set_param(_BACKUP, json.dumps(backup, ensure_ascii=False))
        params.set_param(_MODULE + '.applied_version', '18.0.2.0.0')
        _logger.info('ABSAR reports 18.0.2.0.0 configured: %s active report bindings', len(bound))
        return True
