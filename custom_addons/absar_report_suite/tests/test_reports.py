"""Odoo integration tests; run on staging with --test-enable."""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'absar_reports')
class TestAbsarReports(TransactionCase):
    def test_repeat_setup_and_action_routes(self):
        setup = self.env['absar.report.setup']
        params = self.env['ir.config_parameter'].sudo()
        setup.apply()
        before = params.get_param('absar_report_suite.original_report_actions')
        routes = {r: params.get_param('absar_report_suite.target.' + r) for r in [
            'invoice_report', 'invoice_payment_report', 'purchase_report',
            'quotation_report', 'proforma_report', 'journal_report',
            'certificate_report', 'subcontract_report']}
        setup.apply()
        self.assertEqual(before, params.get_param('absar_report_suite.original_report_actions'))
        for alias, record_id in routes.items():
            self.assertEqual(record_id, params.get_param('absar_report_suite.target.' + alias))
            action = self.env['ir.actions.report'].browse(int(record_id))
            self.assertTrue(action.exists())
            self.assertTrue(action.binding_model_id)
            self.assertTrue(action.report_name.startswith('absar_report_suite.'))

    def test_render_purchase_sale_and_journal(self):
        partner = self.env['res.partner'].create({'name': 'ABSAR Report Test'})
        po = self.env['purchase.order'].create({'partner_id': partner.id})
        so = self.env['sale.order'].create({'partner_id': partner.id})
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'general')], limit=1)
        self.assertTrue(journal, 'Test company needs a general journal')
        move = self.env['account.move'].create({'journal_id': journal.id})
        for alias, record in [('purchase_report', po), ('subcontract_report', po),
                              ('quotation_report', so), ('proforma_report', so),
                              ('journal_report', move)]:
            html, _ = self.env['ir.actions.report']._render_qweb_html(
                'absar_report_suite.' + alias, record.ids)
            self.assertIn(b'Absar Header', html)
            self.assertIn(record.name.encode(), html)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'absar_report_suite.proforma_report', so.ids)
        self.assertIn(b'Pro-Forma Invoice', html)
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'absar_report_suite.journal_report', move.ids)
        self.assertIn(b'Printed by:', html)
        self.assertNotIn(b'Footer Image', html)

    def test_render_invoice_payment_and_certificate(self):
        partner = self.env['res.partner'].create({'name': 'ABSAR Invoice Test'})
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id), ('type', '=', 'sale')], limit=1)
        self.assertTrue(journal, 'Test company needs a sales journal')
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': partner.id, 'journal_id': journal.id})
        for alias in ['invoice_report', 'invoice_payment_report', 'certificate_report']:
            html, _ = self.env['ir.actions.report']._render_qweb_html(
                'absar_report_suite.' + alias, invoice.ids)
            self.assertIn(b'Absar Header', html)
            self.assertIn(partner.name.encode(), html)
