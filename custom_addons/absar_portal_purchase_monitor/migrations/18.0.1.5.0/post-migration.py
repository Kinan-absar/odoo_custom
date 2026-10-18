"""Fail closed if the native-host grants were not retired on upgrade."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    metadata = env['ir.model.data'].search([
        ('module', '=', 'absar_portal_purchase_monitor'),
        ('model', 'in', ['ir.model.access', 'ir.rule']),
    ])
    native_grants = metadata.filtered(lambda rec: rec.name.startswith(('access_native_', 'native_')))
    if native_grants:
        raise RuntimeError('Native Purchase host grants remain; upgrade aborted before activation.')
