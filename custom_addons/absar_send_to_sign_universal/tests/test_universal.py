"""Database/native view regressions; run on Odoo 18 with --test-enable.

These do not send invitations. Offline checks are a separate suite.
"""
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError, UserError, ValidationError


@tagged('post_install', '-at_install')
class TestUniversalIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = cls.env['ir.model']._get('res.partner')
        cls.report = cls.env['ir.actions.report'].create({
            'name': 'Universal Signing Test Report', 'model': 'res.partner',
            'report_type': 'qweb-pdf', 'report_name': 'absar_send_to_sign_universal.test_report',
        })
        cls.config = cls.env['absar.sign.universal.integration'].create({
            'name': 'Test Partner Signing', 'model_id': cls.model.id,
            'report_id': cls.report.id, 'form_view_ids': [(6, 0, [cls.env.ref('base.view_partner_form').id])],
        })

    def test_activation_adds_real_native_button(self):
        self.config.active = True
        view = self.config.generated_view_ids
        self.assertEqual(len(view), 1)
        self.assertIn('type="action"', view.arch_db)
        self.assertIn('name="%s"' % self.config.action_id.id, view.arch_db)
        # This executes native view inheritance and its validation, not a string mock.
        combined = self.env.ref('base.view_partner_form')._get_combined_arch()
        self.assertEqual(len(combined.xpath("//button[@name='%s']" % self.config.action_id.id)), 1)

    def test_deactivation_removes_native_button(self):
        self.config.active = True
        self.config.active = False
        self.assertFalse(self.config.generated_view_ids)
        self.assertFalse(self.config.action_id.binding_model_id)

    def test_repeated_refresh_does_not_duplicate_buttons(self):
        self.config.active = True
        self.config.action_refresh_buttons()
        self.config.action_refresh_buttons()
        self.assertEqual(len(self.config.generated_view_ids), 1)

    def test_wrong_report_model_rejected(self):
        report = self.report.copy({'model': 'res.users'})
        with self.assertRaises(ValidationError):
            self.config.report_id = report

    def test_specialized_model_preserved(self):
        model = self.env['ir.model']._get('purchase.order')
        if not model:
            self.skipTest('Purchase not installed')
        report = self.report.copy({'model': 'purchase.order'})
        with self.assertRaises(ValidationError):
            self.env['absar.sign.universal.integration'].create({
                'name': 'Do not override PO', 'model_id': model.id, 'report_id': report.id,
            })

    def test_user_cannot_generate_views(self):
        user = self.env['res.users'].create({
            'name': 'Universal Signing Reader', 'login': 'universal_signing_reader_test',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.config.with_user(user).action_refresh_buttons()

    def test_multiple_documents_rejected(self):
        self.config.active = True
        partners = self.env['res.partner'].create([{'name': 'Universal Test A'}, {'name': 'Universal Test B'}])
        with self.assertRaises(UserError):
            self.config.action_send(partners)
