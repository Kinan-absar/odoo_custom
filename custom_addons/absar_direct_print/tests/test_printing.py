import json
from types import SimpleNamespace
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tests import tagged
from odoo.exceptions import AccessError, UserError
from ..models.printing import _filter_account_move_reports

@tagged('post_install', '-at_install')
class TestDirectPrint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='print_test_user', groups='absar_direct_print.group_print_user')
        cls.other = new_test_user(cls.env, login='print_test_other', groups='absar_direct_print.group_print_user')
        cls.station = cls.env['absar.print.station'].create({'name':'Test Office','company_id':cls.env.company.id,'allowed_user_ids':[(6,0,[cls.user.id])]})
    def test_station_sender_permissions(self):
        self.station.with_user(self.user)._check_sender()
        with self.assertRaises(AccessError):self.station.with_user(self.other)._check_sender()
        with self.assertRaises(AccessError):self.station.with_user(self.user).action_pair()
    def test_job_visibility_and_no_direct_create(self):
        job=self.env['absar.print.job'].sudo().create({'name':'Test','station_id':self.station.id,'user_id':self.user.id})
        job.with_user(self.user).check_access('read')
        with self.assertRaises(AccessError):job.with_user(self.other).check_access('read')
        with self.assertRaises(AccessError):
            self.env['absar.print.job'].with_user(self.user).create({'name':'Bypass','station_id':self.station.id,'user_id':self.user.id})
        job.with_user(self.user).action_cancel()
        self.assertEqual(job.state,'cancelled')
    def test_foreign_company_station(self):
        company=self.env['res.company'].create({'name':'Other Print Company'})
        station=self.env['absar.print.station'].create({'name':'Other','company_id':company.id})
        with self.assertRaises(AccessError):station.with_user(self.user)._check_sender()
    def test_wizard_ownership(self):
        template=self.env['ir.ui.view'].create({'name':'Print test template','key':'absar_direct_print.test_report','type':'qweb','arch_db':'<t t-name="absar_direct_print.test_report"><div>Print test</div></t>'})
        report=self.env['ir.actions.report'].create({'name':'Test Report','model':'res.partner','report_type':'qweb-pdf','report_name':template.key})
        w=self.env['absar.print.wizard'].with_user(self.user).create({'name':'Test','report_id':report.id,'payload':json.dumps({'context':{},'data':{}})})
        w._report_args()
        action=self.env['absar.print.wizard'].with_user(self.user).open_report({'report_type':'qweb-pdf','report_name':report.report_name,'context':{}})
        self.assertEqual(action['views'],[(False,'form')])
        with self.assertRaises(AccessError):w.with_user(self.other)._report_args()
        with self.assertRaises(UserError):
            self.env['absar.print.wizard'].with_user(self.user).open_report({'report_type':'qweb-text'})
    def test_separate_print_reports_and_record_access(self):
        model = self.env['ir.model']._get('res.partner')
        report = self.env['ir.actions.report'].create({
            'name': 'Bound print test', 'model': 'res.partner', 'report_type': 'qweb-pdf',
            'report_name': 'absar_direct_print.bound_test', 'binding_model_id': model.id,
            'binding_view_types': 'form'})
        wizard_model = self.env['absar.print.wizard'].with_user(self.user)
        self.assertIn(report.id, [r['id'] for r in wizard_model.available_reports('res.partner', 'form')])
        self.assertNotIn(report.id, [r['id'] for r in wizard_model.available_reports('res.partner', 'list')])
        partner = self.env['res.partner'].create({'name': 'Print selection'})
        action = wizard_model.open_for_records('res.partner', [partner.id], 'form')
        self.assertEqual(action['views'], [(False, 'form')])
        wizard = wizard_model.browse(action['res_id'])
        self.assertEqual(wizard._report_args()[1], [partner.id])
        report.groups_id = self.env.ref('absar_direct_print.group_print_manager')
        with self.assertRaises(AccessError):
            wizard.write({'report_id': report.id})
            wizard._report_args()
        with self.assertRaises(UserError):
            wizard_model.open_for_records('res.partner', [], 'form')

    def test_account_move_reports_are_contextual_and_journal_voucher_is_default(self):
        journal = SimpleNamespace(id=1, name='Journal Entries', report_name='absar_report_suite.journal')
        invoice = SimpleNamespace(id=2, name='Invoice', report_name='absar_report_suite.invoice')
        invoice_copy = SimpleNamespace(id=3, name='Invoice copy(1)', report_name='studio_customization.invoice_copy')
        timesheets = SimpleNamespace(id=4, name='Timesheets', report_name='hr_timesheet.report_timesheet')
        reports = [invoice, timesheets, invoice_copy, journal]

        misc_reports = _filter_account_move_reports(reports, {'entry'})
        self.assertEqual(misc_reports, [journal])

        bill_reports = _filter_account_move_reports(reports, {'in_invoice'})
        self.assertEqual(bill_reports, [journal, invoice])

    def _printer_test_wizard(self, station):
        report = self.env['ir.actions.report'].create({
            'name': 'Printer routing test', 'model': 'res.partner', 'report_type': 'qweb-pdf',
            'report_name': 'absar_direct_print.printer_routing_test'})
        return self.env['absar.print.wizard'].with_user(self.user).create({
            'report_id': report.id, 'payload': json.dumps({'context': {}, 'data': {}}),
            'station_id': station.id})

    def test_multiple_printers_and_station_default(self):
        self.station.printer_name = 'Canon MF440 Series'
        self.station._sync_printers(['Canon MF440 Series', 'EPSONC66C03 (L14150 Series)', 'Canon MF440 Series'])
        printers = self.station.printer_ids
        self.assertEqual(len(printers), 2)
        wizard = self._printer_test_wizard(self.station)
        self.assertEqual(wizard._print_destination(), 'Canon MF440 Series')
        epson = printers.filtered(lambda printer: printer.name.startswith('EPSON'))
        wizard.printer_id = epson
        self.assertEqual(wizard._print_destination(), 'EPSONC66C03 (L14150 Series)')
        self.station._sync_printers(['Canon MF440 Series'])
        self.assertFalse(epson.active)
        with self.assertRaises(UserError):
            wizard._print_destination()
        self.station._sync_printers(['Canon MF440 Series', 'EPSONC66C03 (L14150 Series)'])
        self.assertTrue(epson.active)
        self.assertEqual(wizard._print_destination(), epson.name)

    def test_printer_directory_is_read_only_and_station_scoped(self):
        self.station._sync_printers(['Canon'])
        other_station = self.env['absar.print.station'].create({'name': 'Other PC', 'company_id': self.env.company.id})
        other_station._sync_printers(['Epson'])
        wizard = self._printer_test_wizard(self.station)
        wizard.printer_id = other_station.printer_ids
        with self.assertRaises(UserError):
            wizard._print_destination()
        with self.assertRaises(AccessError):
            self.env['absar.print.printer'].with_user(self.user).create({'name': 'Bypass', 'station_id': self.station.id})
        other_company = self.env['res.company'].create({'name': 'Printer Test Company'})
        foreign = self.env['absar.print.station'].create({'name': 'Foreign', 'company_id': other_company.id})
        foreign._sync_printers(['Foreign printer'])
        with self.assertRaises(AccessError):
            foreign.printer_ids.with_user(self.user).check_access('read')

    def test_visibility_survives_discovery_and_canon_is_default(self):
        self.station._sync_printers(['EPSONC66C03 (L14150 Series)', 'Canon MF440 Series', 'Microsoft Print to PDF'])
        wizard = self._printer_test_wizard(self.station)
        self.assertEqual(wizard.printer_id.name, 'Canon MF440 Series')
        hidden = self.station.printer_ids.filtered(lambda printer: printer.name == 'Microsoft Print to PDF')
        hidden.sudo().show_in_wizard = False
        self.station._sync_printers(['EPSONC66C03 (L14150 Series)', 'Canon MF440 Series', 'Microsoft Print to PDF'])
        self.assertFalse(hidden.show_in_wizard)
        wizard.printer_id = hidden
        with self.assertRaises(UserError):
            wizard._print_destination()
        fresh = self._printer_test_wizard(self.station)
        self.assertEqual(fresh.printer_id.name, 'Canon MF440 Series')
        self.station.default_printer_id = self.station.printer_ids.filtered(lambda printer: printer.name.startswith('EPSON'))
        configured = self._printer_test_wizard(self.station)
        self.assertEqual(configured.printer_id, self.station.default_printer_id)
        with self.assertRaises(AccessError):
            hidden.with_user(self.user).write({'show_in_wizard': True})
        with self.assertRaises(AccessError):
            hidden.with_user(self.env.ref('base.user_admin')).write({'name': 'Changed Windows identity'})

    def test_automatic_station_respects_user_preference_and_allowed_users(self):
        self.user.sudo().absar_print_station_id = self.station
        model = self.env['absar.print.wizard'].with_user(self.user)
        self.assertEqual(model._default_station(), self.station)
        self.station.allowed_user_ids = self.other
        self.assertNotEqual(model._default_station(), self.station)
