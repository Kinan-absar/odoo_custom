"""Odoo integration tests; run on staging with --test-enable."""
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged('post_install', '-at_install', 'absar_reports')
class TestAbsarReports(TransactionCase):
    def _action(self, alias):
        record_id = self.env['ir.config_parameter'].sudo().get_param(
            'absar_report_suite.target.' + alias)
        return self.env['ir.actions.report'].browse(int(record_id)).exists()

    def test_repeat_setup_and_action_routes(self):
        setup = self.env['absar.report.setup']
        params = self.env['ir.config_parameter'].sudo()
        setup.apply()
        before = params.get_param('absar_report_suite.original_report_actions')
        routes = {r: params.get_param('absar_report_suite.target.' + r) for r in [
            'invoice_report', 'invoice_payment_report', 'purchase_report', 'rfq_report',
            'quotation_report', 'proforma_report', 'journal_report']}
        setup.apply()
        self.assertEqual(before, params.get_param('absar_report_suite.original_report_actions'))
        for alias, record_id in routes.items():
            self.assertEqual(record_id, params.get_param('absar_report_suite.target.' + alias))
            action = self.env['ir.actions.report'].browse(int(record_id))
            self.assertTrue(action.exists())
            if alias in ('invoice_report', 'invoice_payment_report'):
                self.assertFalse(action.binding_model_id,
                                 'invoice PDFs are selected from the contextual direct-print dialog')
            else:
                self.assertTrue(action.binding_model_id)
            self.assertTrue(action.report_name.startswith('absar_report_suite.') or
                            action.report_name == 'purchase.report_purchaseorder')
        if 'absar.print.wizard' in self.env:
            account_move_bindings = self.env['ir.actions.report'].search([
                ('model', '=', 'account.move'), ('binding_model_id', '!=', False),
                ('binding_type', '=', 'report')])
            self.assertEqual(account_move_bindings, self._action('journal_report'),
                             'Journal Voucher should be the only generic Print action for account moves')

    def test_render_purchase_sale_and_journal(self):
        partner = self.env['res.partner'].create({'name': 'ABSAR Report Test'})
        po = self.env['purchase.order'].create({'partner_id': partner.id})
        so = self.env['sale.order'].create({'partner_id': partner.id})
        project_field = so._fields.get('construction_project_id')
        if project_field:
            project = self.env[project_field.comodel_name].create({'name': 'ABSAR Report Project'})
            so.write({'construction_project_id': project.id})
        else:
            project = self.env['project.project'].create({'name': 'ABSAR Report Project', 'sale_order_id': so.id})
            so.invalidate_recordset(['project_ids'])
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'general')], limit=1)
        self.assertTrue(journal, 'Test company needs a general journal')
        move = self.env['account.move'].create({'journal_id': journal.id})
        for alias, record in [('purchase_report', po), ('rfq_report', po),
                              ('quotation_report', so), ('proforma_report', so),
                              ('journal_report', move)]:
            html, _ = self.env['ir.actions.report']._render_qweb_html(
                self._action(alias), record.ids)
            self.assertIn(b'Absar Header', html)
            self.assertIn(record.name.encode(), html)
        purchase_html, _ = self.env['ir.actions.report']._render_qweb_html(
            self._action('purchase_report'), po.ids)
        self.assertIn(b'Request for Quotation #', purchase_html)
        rfq_html, _ = self.env['ir.actions.report']._render_qweb_html(
            self._action('rfq_report'), po.ids)
        self.assertIn(b'Request for Quotation #', rfq_html)
        self.assertIn(b'absar-po-white', rfq_html)
        sale_html, _ = self.env['ir.actions.report']._render_qweb_html(
            self._action('quotation_report'), so.ids)
        self.assertIn(b'Project:', sale_html)
        self.assertIn(project.name.encode(), sale_html)
        self.assertIn(b'ABSAR Report Project', sale_html)
        self.assertIn(b'absar-sale-document', sale_html)
        self.assertIn(b'o_ignore_layout_styling absar-unified-table', sale_html)
        self.assertNotIn(b'table table-sm o_main_table', sale_html)
        self.assertIn(b'o_ignore_layout_styling', sale_html)
        self.assertIn(b'border-bottom:1px solid #177b83', sale_html)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            self._action('proforma_report'), so.ids)
        self.assertIn(b'Pro-Forma Invoice', html)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            self._action('journal_report'), move.ids)
        self.assertIn(b'Printed by:', html)
        self.assertNotIn(b'Footer Image', html)

    def test_render_invoice_and_invoice_payment(self):
        partner = self.env['res.partner'].create({'name': 'ABSAR Invoice Test'})
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1)
        self.assertTrue(journal, 'Test company needs a sales journal')
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id, 'journal_id': journal.id})
        for alias in ['invoice_report', 'invoice_payment_report']:
            html, _ = self.env['ir.actions.report']._render_qweb_html(
                self._action(alias), invoice.ids)
            self.assertIn(b'Absar Header', html)
            self.assertIn(partner.name.encode(), html)


    def test_obsolete_subcontract_reports_have_no_print_actions(self):
        params = self.env['ir.config_parameter'].sudo()
        actions = self.env['ir.actions.report'].sudo()
        setup = self.env['absar.report.setup']
        retired_actions = actions.browse()
        for model, name, report_name in [
            ('purchase.order', 'عقد مقاولة من الباطن / Subcontract Agreement', 'absar_report_suite.subcontract'),
            ('account.move', 'Subcontractor Payment Certificate', 'absar_report_suite.certificate'),
        ]:
            retired_actions |= actions.create({
                'name': name, 'model': model, 'report_type': 'qweb-pdf',
                'report_name': report_name, 'binding_model_id': self.env['ir.model']._get(model).id,
                'binding_type': 'report', 'binding_view_types': 'list,form',
            })
        setup.apply()
        self.assertFalse(retired_actions.exists(), 'obsolete report actions must be deleted, not just unbound')
        for alias in ['certificate_report', 'subcontract_report']:
            self.assertFalse(params.get_param('absar_report_suite.target.' + alias))
        for model, report_names in [
            ('purchase.order', ['absar_report_suite.subcontract', 'absar.subcontract']),
            ('account.move', ['absar_report_suite.certificate', 'account.report_invoice_copy_1_copy_1_copy_3']),
        ]:
            for report_name in report_names:
                self.assertFalse(actions.search([('model', '=', model), ('report_name', '=', report_name),
                                                 ('binding_model_id', '!=', False)]))
        views = self.env['ir.ui.view'].sudo().with_context(active_test=False)
        retired_keys = ['absar_report_suite.subcontract', 'absar_report_suite.subcontract_document',
                        'absar_report_suite.subcontract_tax_totals', 'absar_report_suite.certificate',
                        'absar_report_suite.certificate_bilingual']
        self.assertFalse(views.search([('key', 'in', retired_keys)]))

    def test_duplicate_tax_invoice_header_button_is_hidden(self):
        view = self.env['ir.ui.view'].sudo().create({
            'name': 'ABSAR print button cleanup fixture', 'model': 'account.move',
            'type': 'form', 'arch_db': '<form><header><button name="x" string="Print Tax Inv"/></header></form>',
        })
        self.env['absar.report.setup']._hide_tax_invoice_buttons()
        self.assertIn('invisible="True"', view.arch_db)

    def test_cleanup_removes_unused_and_preserves_references(self):
        views = self.env['ir.ui.view']
        retired = views.create({
            'name': 'ABSAR cleanup disposable wrapper', 'type': 'qweb',
            'key': 'purchase.report_purchaseorder_copy_1',
            'arch_db': '<t t-name="purchase.report_purchaseorder_copy_1"><p>old</p></t>',
        })
        dependency = views.create({
            'name': 'ABSAR cleanup dependency', 'type': 'qweb',
            'key': 'purchase.report_purchaseorder_copy_2',
            'arch_db': '<t t-name="purchase.report_purchaseorder_copy_2"><p>keep</p></t>',
        })
        retained = views.create({
            'name': 'Unrelated retained report', 'type': 'qweb',
            'key': 'absar_cleanup_test.retained',
            'arch_db': '<t t-name="absar_cleanup_test.retained"><t t-call="purchase.report_purchaseorder_copy_2"/></t>',
        })
        system = views.create({
            'name': 'Protected owner fixture', 'type': 'qweb',
            'key': 'purchase.report_purchaseorder_copy_3',
            'arch_db': '<t t-name="purchase.report_purchaseorder_copy_3"><p>system</p></t>',
        })
        self.env['ir.model.data'].create({
            'module': 'account', 'name': 'absar_cleanup_guard_fixture',
            'model': 'ir.ui.view', 'res_id': system.id,
        })
        action = self.env['ir.actions.report'].create({
            'name': 'Unused retired action', 'model': 'purchase.order',
            'report_type': 'qweb-pdf', 'report_name': 'purchase.report_purchaseorder_copy_1',
        })
        self.env['absar.report.setup'].apply()
        self.assertFalse(retired.exists())
        self.assertFalse(action.exists())
        self.assertTrue(dependency.exists())
        self.assertTrue(retained.exists())
        self.assertTrue(system.exists())
        self.assertTrue(self.env.ref('web.external_layout_wave').exists())
        self.assertTrue(self.env.ref('absar_report_suite.purchase').exists())
        self.env['absar.report.setup'].apply()
        self.assertTrue(dependency.exists())

    def test_legacy_po_signing_reference_and_pdf(self):
        reports = self.env['ir.actions.report']
        self.assertEqual(reports._get_report('purchase.report_purchaseorder'),
                         self._action('purchase_report'))
        partner = self.env['res.partner'].create({'name': 'Signing Filename Supplier'})
        po = self.env['purchase.order'].create({'partner_id': partner.id})
        filename = safe_eval(self._action('purchase_report').print_report_name, {'object': po})
        self.assertEqual(self._action('purchase_report').print_report_name, 'object._absar_report_filename()')
        self.assertEqual(filename, po._absar_report_filename())
        self.assertIn(po.name, filename)
        self.assertIn(partner.name, filename)
        pdf, fmt = reports._render_qweb_pdf('purchase.report_purchaseorder', po.ids)
        self.assertEqual(fmt, 'pdf')
        self.assertTrue(pdf.startswith(b'%PDF'))
        # Exercise the signing package builder without creating a request or sending mail.
        if hasattr(po, '_absar_build_signing_package_pdf'):
            package = po._absar_build_signing_package_pdf()
            if isinstance(package, tuple):
                package = package[0]
            self.assertTrue(package.startswith(b'%PDF'))

    def test_cleanup_of_module_owned_duplicate_and_upgrade_tracking(self):
        metadata = self.env['ir.model.data']
        alias = 'purchase_report'
        old_alias = metadata.search([('module', '=', 'absar_report_suite'), ('name', '=', alias)])
        if old_alias:
            self.skipTest('This database uses the module action as its only canonical PO action')
        target = self._action(alias)
        duplicate = target.copy({'binding_model_id': False, 'report_name': 'absar_report_suite.purchase'})
        metadata.create({'module': 'absar_report_suite', 'name': alias,
                         'model': 'ir.actions.report', 'res_id': duplicate.id, 'noupdate': False})
        self.env['absar.report.setup'].apply()
        self.assertFalse(duplicate.exists())
        self.assertTrue(target.exists())
        self.assertEqual(self._action(alias), target)
        self.env['absar.report.setup'].apply()
        self.assertFalse(self.env.ref('absar_report_suite.' + alias, raise_if_not_found=False))
