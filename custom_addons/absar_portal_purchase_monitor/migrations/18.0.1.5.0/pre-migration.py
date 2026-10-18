"""Retire the 1.4 native host before its Python model extensions disappear.

Delete only ACLs/rules whose XML identifiers belong to this addon and use the
native-host prefixes. SQL is intentional in pre-migration: the replacement
registry is not yet initialized. Existing role assignments and business rows
are untouched. This is a no-op when upgrading from 1.2/1.3.
"""
MODULE = 'absar_portal_purchase_monitor'


def retire_native_host(cr):
    for model, table, prefix in (
        ('ir.model.access', 'ir_model_access', 'access_native_'),
        ('ir.rule', 'ir_rule', 'native_'),
    ):
        # Names come only from constants above; module/prefix remain bound parameters.
        cr.execute('DELETE FROM ' + table + ''' WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = %s AND model = %s AND name LIKE %s ESCAPE '!'
        )''', [MODULE, model, prefix.replace('_', '!_') + '%'])
        cr.execute('''DELETE FROM ir_model_data
            WHERE module = %s AND model = %s AND name LIKE %s ESCAPE '!'
        ''', [MODULE, model, prefix.replace('_', '!_') + '%'])
    # Retire inherited presentation, MR button, return wizard and QWeb host views.
    # The main PO review view is replaced by the portal version during data load.
    cr.execute('''UPDATE ir_ui_view SET active = false WHERE id IN (
        SELECT res_id FROM ir_model_data WHERE module = %s AND model = 'ir.ui.view'
        AND name IN ('purchase_form_native_presentation', 'product_form_native_presentation',
                     'material_request_list_native_purchase', 'portal_return_form', 'native_purchase_shell')
    )''', [MODULE])


def migrate(cr, version):
    retire_native_host(cr)
