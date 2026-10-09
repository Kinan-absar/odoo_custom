"""Install/update the audited ABSAR report set without staging database IDs."""

import base64
import json
import logging
from pathlib import Path

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parents[1]
_MODULE = 'absar_report_suite'


class AbsarReportMigration(models.AbstractModel):
    _name = 'absar.report.migration'
    _description = 'ABSAR report installation and exact duplicate cleanup'

    def _ref(self, xmlid, model):
        record = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else False
        if record and record._name != model:
            raise UserError('Unexpected model for external ID %s' % xmlid)
        return record.exists() if record else self.env[model].browse()

    def _alias(self, alias, record):
        # Only newly created records are owned by this module. Existing module/
        # Studio XML IDs remain attached to their existing records and buttons.
        module, name = _MODULE, alias
        data = self.env['ir.model.data'].sudo()
        existing = data.search([('module', '=', module), ('name', '=', name)])
        values = {'model': record._name, 'res_id': record.id, 'noupdate': True}
        if existing:
            existing.write(values)
        else:
            data.create(dict(values, module=module, name=name))

    def _view(self, item):
        view = self._ref(item.get('xmlid'), 'ir.ui.view')
        if not view:
            view = self._ref(_MODULE + '.' + item.get('alias', 'unused'), 'ir.ui.view')
        if not view:
            matches = self.env['ir.ui.view'].with_context(active_test=False).search([
                ('key', '=', item['key']), ('type', '=', 'qweb')])
            active = matches.filtered('active')
            if len(active) == 1:
                view = active
            elif len(matches) == 1:
                view = matches
            elif matches:
                raise UserError('Ambiguous report template: %s' % item['key'])
        return view

    def _report(self, item):
        report = self._ref(item.get('xmlid'), 'ir.actions.report')
        if not report:
            report = self._ref(_MODULE + '.' + item['alias'], 'ir.actions.report')
        if not report:
            # Exact display name first preserves the original Invoice action
            # and the one PI action used by the existing Print PI button.
            report = self.env['ir.actions.report'].search([
                ('model', '=', item['model']), ('name', '=', item['name'])])
        if not report:
            report = self.env['ir.actions.report'].search([
                ('model', '=', item['model']),
                ('report_name', 'in', [item['report_name']] + item.get('old_reports', []))])
        if len(report) > 1:
            raise UserError('Ambiguous report action: %s' % item['name'])
        if report and report.model != item['model']:
            raise UserError('Unexpected report model: %s' % item['name'])
        return report

    def _preflight(self, manifest):
        missing = []
        for model, names in manifest['required_fields'].items():
            missing += [model + '.' + name for name in names if name not in self.env[model]._fields]
        if missing:
            raise UserError('Install the existing ABSAR business customizations first. Missing fields: ' + ', '.join(missing))
        company = self.env['res.company'].sudo().search([('name', '=', 'ABSAR ALOMRAN COMPANY')])
        if len(company) != 1:
            raise UserError('This package is for the existing ABSAR ALOMRAN COMPANY database.')
        wave = self._ref('web.external_layout_wave', 'ir.ui.view')
        if not wave or 'Absar Header' not in wave.arch_db:
            raise UserError('The expected ABSAR company external layout is missing. Review the target database before installation.')
        if company.external_report_layout_id != wave:
            raise UserError('ABSAR is not using the expected company external layout. Review the target company layout before installation.')
        for item in manifest['views']:
            etree.fromstring((_ROOT / item['file']).read_bytes())
            self._view(item)
            if item.get('inherit_xmlid') and not self._ref(item['inherit_xmlid'], 'ir.ui.view'):
                raise UserError('Missing parent view: %s' % item['inherit_xmlid'])
        for item in manifest['reports']:
            self._report(item)
        return company

    def _retired(self, manifest):
        views = self.env['ir.ui.view'].with_context(active_test=False).search([
            ('type', '=', 'qweb'), ('key', 'in', [v['key'] for v in manifest['retired_views']])])
        actions = self.env['ir.actions.report'].search([
            ('report_name', 'in', manifest['retired_action_templates'])])
        for xmlid in manifest['retired_action_xmlids']:
            actions |= self._ref(xmlid, 'ir.actions.report')
        keeper = self._view(next(v for v in manifest['views'] if v['key'] == 'absar.subcontract'))
        if keeper:
            views |= self.env['ir.ui.view'].with_context(active_test=False).search([
                ('key', '=', 'absar.subcontract'), ('active', '=', False), ('id', '!=', keeper.id)])
        return views, actions

    def _snapshot(self, manifest, views, actions):
        all_views = views
        all_actions = actions
        for item in manifest['views']:
            all_views |= self._view(item)
        for item in manifest['reports']:
            all_actions |= self._report(item)
        for xmlid in manifest['unbound_report_xmlids']:
            all_actions |= self._ref(xmlid, 'ir.actions.report')
        # Save a before-state for inspection; a full Odoo.sh DB backup is still
        # the supported rollback, since original record IDs may be referenced.
        payload = {
            'version': manifest['version'], 'created_at': str(fields.Datetime.now()),
            'views': all_views.with_context(lang=None).read([
                'name', 'key', 'type', 'arch_db', 'inherit_id', 'mode', 'priority', 'active']),
            'actions': all_actions.read([
                'name', 'model', 'report_name', 'report_file', 'report_type',
                'paperformat_id', 'binding_model_id', 'binding_type',
                'binding_view_types', 'print_report_name', 'attachment_use', 'attachment', 'groups_id']),
            'external_ids': self.env['ir.model.data'].search([
                '|', '&', ('model', '=', 'ir.ui.view'), ('res_id', 'in', all_views.ids),
                '&', ('model', '=', 'ir.actions.report'), ('res_id', 'in', all_actions.ids),
            ]).read(['module', 'name', 'model', 'res_id', 'noupdate']),
            'paperformats': self.env['report.paperformat'].search([
                ('name', '=', 'ABSAR Journal Voucher A4')]).read([
                    'name', 'format', 'orientation', 'margin_top', 'margin_bottom',
                    'margin_left', 'margin_right', 'header_line', 'header_spacing', 'dpi']),
        }
        attachment = self.env['ir.attachment'].sudo().create({
            'name': 'ABSAR report before-state %s.json' % fields.Datetime.now(),
            'type': 'binary', 'mimetype': 'application/json',
            'datas': base64.b64encode(json.dumps(payload, ensure_ascii=False, default=str).encode()),
            'res_model': 'ir.module.module',
            'res_id': self.env['ir.module.module'].search([('name', '=', _MODULE)], limit=1).id,
        })
        return attachment

    def _assets(self):
        for alias, filename in [('letterhead_image', 'letterhead.png'),
                                ('footer_image', 'footer.png'), ('stamp_image', 'stamp.png')]:
            values = {'name': 'ABSAR ' + filename, 'type': 'binary', 'mimetype': 'image/png',
                      'datas': base64.b64encode((_ROOT / 'static/img' / filename).read_bytes())}
            record = self._ref(_MODULE + '.' + alias, 'ir.attachment')
            if record:
                record.sudo().write(values)
            else:
                record = self.env['ir.attachment'].sudo().create(values)
                self._alias(alias, record)

    def _papers(self):
        papers = {}
        for alias, values in {
            'business': dict(name='ABSAR Business A4', margin_top=45, margin_bottom=32,
                             margin_left=4, margin_right=4, header_spacing=40),
            'journal': dict(name='ABSAR Journal Voucher A4', margin_top=45, margin_bottom=10,
                            margin_left=7, margin_right=7, header_spacing=40),
        }.items():
            values.update(format='A4', orientation='Portrait', header_line=False, dpi=90)
            record = self._ref(_MODULE + '.' + alias + '_paperformat', 'report.paperformat')
            if not record and alias == 'journal':
                record = self.env['report.paperformat'].search([('name', '=', values['name'])])
                if len(record) > 1:
                    raise UserError('Ambiguous ABSAR Journal Voucher paper format')
            if record:
                record.write(values)
            else:
                record = self.env['report.paperformat'].create(values)
                self._alias(alias + '_paperformat', record)
            papers[alias] = record
        return papers

    def _apply_views(self, manifest):
        for item in manifest['views']:
            record = self._view(item)
            values = {'name': item['name'], 'key': item['key'], 'type': 'qweb',
                      'arch_db': (_ROOT / item['file']).read_text(encoding='utf-8'), 'active': True}
            if item.get('inherit_xmlid'):
                values.update(inherit_id=self.env.ref(item['inherit_xmlid']).id, mode='extension')
            else:
                values.update(inherit_id=False, mode='primary')
            if record:
                record.with_context(lang=None).write(values)
            else:
                record = self.env['ir.ui.view'].with_context(lang=None).create(values)
                self._alias(item['alias'], record)

    def _apply_actions(self, manifest, papers):
        keep = self.env['ir.actions.report'].browse()
        for item in manifest['reports']:
            record = self._report(item)
            values = {'name': item['name'], 'model': item['model'],
                      'report_name': item['report_name'], 'report_file': item['report_name'],
                      'report_type': 'qweb-pdf', 'paperformat_id': papers[item['paper']].id,
                      'binding_type': 'report', 'binding_view_types': 'list,form',
                      'binding_model_id': self.env['ir.model']._get(item['model']).id if item['bound'] else False,
                      'attachment_use': False}
            if item.get('print_report_name'):
                values['print_report_name'] = item['print_report_name']
            elif not record and item['model'] == 'account.move':
                values['print_report_name'] = 'object._get_report_base_filename()'
            if record:
                record.write(values)
            else:
                record = self.env['ir.actions.report'].create(values)
                self._alias(item['alias'], record)
            keep |= record
        for xmlid in manifest['unbound_report_xmlids']:
            report = self._ref(xmlid, 'ir.actions.report')
            if report and report not in keep:
                report.write({'binding_model_id': False})
        return keep

    def _check_cleanup_references(self, doomed_views, doomed_actions):
        view_model = self.env['ir.ui.view'].with_context(active_test=False)
        children = view_model.search([('inherit_id', 'in', doomed_views.ids), ('id', 'not in', doomed_views.ids)])
        if children:
            raise UserError('Cleanup would remove unlisted inherited views: %s' % ', '.join(children.mapped('name')))
        keys = set(doomed_views.mapped('key'))
        # Surplus records can share a key with the retained active wrapper.
        # Deleting that inactive record does not delete the canonical key.
        live_keys = set(view_model.search([
            ('active', '=', True), ('id', 'not in', doomed_views.ids),
            ('key', 'in', list(keys))]).mapped('key'))
        keys -= live_keys
        names = set(doomed_actions.mapped('report_name'))
        action_data = self.env['ir.model.data'].search([
            ('model', '=', 'ir.actions.report'), ('res_id', 'in', doomed_actions.ids)])
        old_xmlids = {row.module + '.' + row.name for row in action_data}
        for view in view_model.search([('active', '=', True), ('id', 'not in', doomed_views.ids)]):
            try:
                tree = etree.fromstring(view.arch_db.encode())
            except (etree.XMLSyntaxError, AttributeError):
                continue
            calls = set(tree.xpath('//@t-call'))
            if calls & (keys | names):
                raise UserError('Active view %s still uses a retired report: %s' % (view.name, ', '.join(calls & (keys | names))))
            for button in tree.xpath("//button[@type='action']"):
                name = button.get('name', '')
                if ((name.isdigit() and int(name) in doomed_actions.ids)
                        or any(name == '%%(%s)d' % xmlid for xmlid in old_xmlids)):
                    raise UserError('Active button in %s still uses a retired action; rebind it before installing.' % view.name)
        survivors = self.env['ir.actions.report'].search([('id', 'not in', doomed_actions.ids), ('report_name', 'in', list(keys))])
        if survivors:
            raise UserError('A retained report action still uses a retired template: ' + ', '.join(survivors.mapped('name')))

    @api.model
    def apply_report_suite(self):
        """Called by XML data on installation and every module update."""
        if not self.env.su and not self.env.user.has_group('base.group_system'):
            raise AccessError('Only Settings administrators can apply the ABSAR report migration.')
        manifest = json.loads((_ROOT / 'data/report_manifest.json').read_text(encoding='utf-8'))
        self._preflight(manifest)
        doomed_views, doomed_actions = self._retired(manifest)
        snapshot = self._snapshot(manifest, doomed_views, doomed_actions)
        self._assets()
        papers = self._papers()
        self._apply_views(manifest)
        keep = self._apply_actions(manifest, papers)
        # The subcontract action is reused when it already exists. Remove only
        # surplus inactive wrapper records, never the active canonical one.
        keeper = self._view(next(v for v in manifest['views'] if v['key'] == 'absar.subcontract'))
        duplicates = self.env['ir.ui.view'].with_context(active_test=False).search([
            ('key', '=', 'absar.subcontract'), ('active', '=', False), ('id', '!=', keeper.id)])
        doomed_views |= duplicates
        # Never remove a reused Invoice/PI/JV action, even if its old template
        # belonged to the exact retired list before it was rebound above.
        doomed_actions -= keep
        self._check_cleanup_references(doomed_views, doomed_actions)
        doomed_actions.unlink()
        # ir.ui.view inherits cascade, so validate children before a single
        # ORM unlink over the complete approved set.
        doomed_views.unlink()
        self.env['ir.config_parameter'].sudo().set_param(_MODULE + '.applied_version', manifest['version'])
        self.env['ir.config_parameter'].sudo().set_param(_MODULE + '.last_snapshot_attachment', snapshot.id)
        _logger.info('ABSAR report suite applied: %s views, %s report actions; before-state attachment %s',
                     len(manifest['views']), len(manifest['reports']), snapshot.id)
        return True
