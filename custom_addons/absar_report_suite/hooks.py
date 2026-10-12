"""Restore existing report actions when the addon is uninstalled."""
import json


def uninstall_hook(env):
    params = env['ir.config_parameter'].sudo()
    key = 'absar_report_suite.original_report_actions'
    backup = json.loads(params.get_param(key, '{}'))
    for record_id, values in backup.items():
        record = env['ir.actions.report'].sudo().browse(int(record_id)).exists()
        if not record:
            continue
        for field, model in [('paperformat_id', 'report.paperformat'), ('binding_model_id', 'ir.model')]:
            if values.get(field) and not env[model].sudo().browse(values[field]).exists():
                values[field] = False
        record.write(values)
    params.search(['|', ('key', 'in', [key, 'absar_report_suite.applied_version']),
                   ('key', '=like', 'absar_report_suite.target.%')]).unlink()
