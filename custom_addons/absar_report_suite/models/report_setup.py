"""Reuse existing action IDs; create an action only when no compatible one exists."""
import json
import logging
from pathlib import Path
from odoo import api, models
from odoo.exceptions import AccessError
from .report_cleanup import cleanup_reports

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
        metadata = env['ir.model.data'].sudo()
        config = json.loads((Path(__file__).resolve().parents[1] / 'data/integration.json').read_text())
        backup = json.loads(params.get_param(_BACKUP, '{}'))
        action_ids = metadata.search([('module', '=', _MODULE), ('model', '=', 'ir.actions.report')])
        # Existing module actions no longer have declarative XML records. Protect
        # referenced/fallback records from Odoo's end-of-upgrade XML garbage collector.
        action_ids.write({'noupdate': True})
        owned = actions.browse(action_ids.mapped('res_id')).exists()
        bound = actions.browse()
        routes = {}
        duplicates = actions.browse()

        def remember(record):
            key = str(record.id)
            if key not in backup and record not in owned:
                values = record.read(_FIELDS)[0]
                values.pop('id', None)
                for field in ['paperformat_id', 'binding_model_id']:
                    values[field] = values[field][0] if values[field] else False
                backup[key] = values

        for item in config['reports']:
            canonical = env.ref(_MODULE + '.' + item['alias'], raise_if_not_found=False)
            preferred = env.ref(item['xmlid'], raise_if_not_found=False) if item.get('xmlid') else False
            if preferred and (preferred._name != 'ir.actions.report' or preferred.model != item['model']):
                preferred = False
            candidates = actions.search([
                ('model', '=', item['model']), ('id', 'not in', owned.ids),
                '|', ('report_name', 'in', [item['legacy_report'], item['report_name']] + item.get('old_reports', [])),
                ('name', '=', item['name']),
            ], order='id')
            saved_id = params.get_param(_MODULE + '.target.' + item['alias'])
            saved = actions.browse(int(saved_id)).exists() if saved_id and saved_id.isdigit() else False
            if saved and saved.model != item['model']:
                saved = False
            # Prefer a previously selected non-owned action. Reuse a module-owned
            # fallback only if no pre-existing action can be reused.
            target = (saved if saved and saved not in owned else False) or preferred or candidates[:1] or saved or canonical
            values = {
                'name': item['name'], 'model': item['model'], 'report_type': 'qweb-pdf',
                'report_name': item['report_name'], 'report_file': item['report_name'],
                'paperformat_id': env.ref(_MODULE + '.' + item['paper'] + '_paperformat').id,
                'binding_model_id': env['ir.model']._get(item['model']).id,
                'binding_type': 'report', 'binding_view_types': 'list,form', 'attachment_use': False,
            }
            previous = backup.get(str(target.id), {}) if target else {}
            filename = previous.get('print_report_name') or (target.print_report_name if target else False)
            if item['alias'] == 'purchase_report':
                filename = 'object._absar_report_filename()'
            values['print_report_name'] = filename or item.get('print_report_name') or (
                'object.name' if item['model'] == 'sale.order' else 'object._get_report_base_filename()')
            if target:
                remember(target)
                target.write(values)
            else:
                target = actions.create(values)
                metadata.create({'module': _MODULE, 'name': item['alias'],
                                 'model': 'ir.actions.report', 'res_id': target.id, 'noupdate': True})
                owned |= target
            routes[item['alias']] = target
            params.set_param(_MODULE + '.target.' + item['alias'], str(target.id))
            bound |= target
            duplicate = candidates - target
            if canonical and canonical != target:
                duplicate |= canonical
            for record in duplicate:
                remember(record)
                record.write({'binding_model_id': False})
            duplicates |= duplicate

        standard = {
            'account.account_invoices': 'invoice_payment_report',
            'account.account_invoices_without_payment': 'invoice_report',
            'sale.action_report_saleorder': 'quotation_report',
            'sale.action_report_pro_forma_invoice': 'proforma_report',
        }
        protected = bound
        for xmlid, alias in standard.items():
            report = env.ref(xmlid, raise_if_not_found=False)
            if not report:
                continue
            target = routes[alias]
            remember(report)
            values = {'report_name': target.report_name, 'report_file': target.report_file,
                      'paperformat_id': target.paperformat_id.id, 'attachment_use': False}
            if report not in bound:
                values['binding_model_id'] = False
            report.write(values)
            protected |= report

        params.set_param(_BACKUP, json.dumps(backup, ensure_ascii=False))
        cleanup_reports(env, config, protected, duplicate_action_ids=duplicates.ids)
        params.set_param(_MODULE + '.applied_version', '18.0.2.0.8')
        _logger.info('ABSAR reports 18.0.2.0.8 configured: %s active report bindings', len(bound))
        return True
