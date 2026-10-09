"""Exact custom-report cleanup after successful report rebinding."""
import base64
import json
import re
from lxml import etree
from odoo import fields
from .cleanup_plan import plan_cleanup


def cleanup_reports(env, config, keep):
    reports = env['ir.actions.report'].sudo().search([])
    views = env['ir.ui.view'].sudo().with_context(active_test=False).search([('type', '=', 'qweb')])
    all_ui_views = env['ir.ui.view'].sudo().with_context(active_test=False).search([])
    ids = env['ir.model.data'].sudo().search([
        ('model', 'in', ['ir.ui.view', 'ir.actions.report'])])
    owners, xmlids = {}, {}
    for row in ids:
        node = (row.model, row.res_id)
        owners.setdefault(node, set()).add(row.module)
        xmlids.setdefault(node, set()).add(row.module + '.' + row.name)
    retired_keys = {row['key'] for row in config['retired_views']}
    retired_xmlids = set(config['retired_xmlids'])
    candidates = {('ir.ui.view', view.id) for view in views if view.key in retired_keys}
    candidates |= {('ir.actions.report', report.id) for report in reports
                   if report.report_name in config['retired_templates']
                   or xmlids.get(('ir.actions.report', report.id), set()) & retired_xmlids}
    protected = {('ir.actions.report', record.id) for record in keep}
    protected |= {('ir.ui.view', view.id) for view in views
                  if view.key and view.key.startswith('absar_report_suite.')}
    targets = {}
    for view in views:
        node = ('ir.ui.view', view.id)
        if view.key:
            targets.setdefault(view.key, set()).add(node)
        for xmlid in xmlids.get(node, ()):
            targets.setdefault(xmlid, set()).add(node)
    action_ids = {report.id for report in reports}
    action_xmlids = {xmlid: ('ir.actions.report', report.id) for report in reports
                     for xmlid in xmlids.get(('ir.actions.report', report.id), ())}
    references = []
    for report in reports:
        for target in targets.get(report.report_name, ()):
            references.append((('ir.actions.report', report.id), target))
    for view in all_ui_views:
        consumer = ('ir.ui.view', view.id)
        if view.inherit_id:
            references.append((consumer, ('ir.ui.view', view.inherit_id.id)))
        try:
            tree = etree.fromstring((view.arch_db or '<data/>').encode())
        except (etree.XMLSyntaxError, ValueError):
            # An unreadable retained architecture cannot prove non-use.
            for candidate in candidates:
                references.append((consumer, candidate))
            continue
        for call in tree.xpath('//@t-call|//@t-inherit'):
            for target in targets.get(call, ()):
                references.append((consumer, target))
        for button in tree.xpath("//*[@type='action']"):
            name = button.get('name', '')
            if name.isdigit() and int(name) in action_ids:
                references.append((consumer, ('ir.actions.report', int(name))))
            else:
                match = re.fullmatch(r'%\((.+)\)d', name)
                xmlid = match.group(1) if match else name
                if xmlid in action_xmlids:
                    references.append((consumer, action_xmlids[xmlid]))
        # Protect references embedded in contexts and expressions as XML IDs.
        arch = view.arch_db or ''
        for node in candidates:
            if any(re.search(r"(?<![\w.])" + re.escape(xmlid) + r"(?![\w.])", arch)
                   for xmlid in xmlids.get(node, ())):
                references.append((consumer, node))
    for menu in env['ir.ui.menu'].sudo().with_context(active_test=False).search([('action', '!=', False)]):
        action = menu.action
        if action and action._name == 'ir.actions.report':
            references.append((None, ('ir.actions.report', action.id)))
    for server in env['ir.actions.server'].sudo().search([('state', '=', 'code')]):
        code = server.code or ''
        for node in candidates:
            if any(xmlid in code for xmlid in xmlids.get(node, ())):
                references.append((None, node))
            if node[0] == 'ir.ui.view' and any(key in code for key, nodes in targets.items() if node in nodes):
                references.append((None, node))
            if re.search(r'\bbrowse\(\s*' + str(node[1]) + r'\s*\)', code):
                references.append((None, node))
    # Preserve stored relations from business settings, mail templates and other
    # installed models, even when the old action is hidden from Print menus.
    relation_fields = env['ir.model.fields'].sudo().search([
        ('relation', 'in', ['ir.ui.view', 'ir.actions.report']),
        ('ttype', 'in', ['many2one', 'many2many']), ('store', '=', True),
    ])
    for field in relation_fields:
        if field.model == 'ir.ui.view' and field.name == 'inherit_id':
            continue
        if field.model not in env:
            continue
        model = env[field.model].sudo().with_context(active_test=False)
        if field.name not in model._fields:
            continue
        target_ids = [record_id for model_name, record_id in candidates if model_name == field.relation]
        if not target_ids:
            continue
        for consumer in model.search([(field.name, 'in', target_ids)]):
            for target in consumer[field.name]:
                references.append(((field.model, consumer.id), (field.relation, target.id)))
    removable, reasons = plan_cleanup(candidates, owners, protected, references)
    doomed_views = views.browse(sorted(i for model, i in removable if model == 'ir.ui.view'))
    doomed_reports = reports.browse(sorted(i for model, i in removable if model == 'ir.actions.report'))
    summary = {
        'version': '18.0.2.0.1', 'date': str(fields.Datetime.now()),
        'deleted_actions': doomed_reports.read(['name', 'model', 'report_name']),
        'deleted_views': doomed_views.read(['name', 'key']),
        'preserved': [{'model': model, 'id': record_id, 'reason': reason}
                      for (model, record_id), reason in sorted(reasons.items())],
    }
    if removable:
        payload = dict(summary)
        payload['view_before_state'] = doomed_views.with_context(lang=None).read([
            'name', 'key', 'type', 'arch_db', 'inherit_id', 'mode', 'priority', 'active'])
        payload['action_before_state'] = doomed_reports.read([
            'name', 'model', 'report_name', 'report_file', 'report_type',
            'paperformat_id', 'binding_model_id', 'binding_type', 'print_report_name'])
        payload['external_ids'] = ids.filtered(lambda row: (row.model, row.res_id) in removable).read([
            'module', 'name', 'model', 'res_id', 'noupdate'])
        attachment = env['ir.attachment'].sudo().create({
            'name': 'ABSAR retired report before-state %s.json' % fields.Datetime.now(),
            'type': 'binary', 'mimetype': 'application/json',
            'datas': base64.b64encode(json.dumps(payload, ensure_ascii=False, default=str).encode()),
        })
        summary['before_state_attachment_id'] = attachment.id
        doomed_reports.unlink()
        # The graph excludes parents with surviving children, avoiding cascade loss.
        doomed_views.unlink()
    params = env['ir.config_parameter'].sudo()
    params.set_param('absar_report_suite.last_cleanup', json.dumps(summary, ensure_ascii=False, default=str))
    if removable:
        params.set_param('absar_report_suite.last_deletion_cleanup', json.dumps(summary, ensure_ascii=False, default=str))
    return summary
