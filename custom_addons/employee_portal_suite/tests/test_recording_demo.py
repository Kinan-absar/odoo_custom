from unittest.mock import patch
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError


@tagged('post_install', '-at_install')
class TestRecordingDemo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref('base.user_admin')
        cls.batch = cls.env['employee.portal.recording.demo'].with_user(cls.admin).create({
            'name': 'Integration test batch', 'confirmed_demo': True,
            'include_draft_documents': False,
        })
        cls.batch.action_create_samples()

    def test_quotations_and_invoice_submission(self):
        requests = self.batch.material_request_ids
        self.assertEqual(len(requests), 28)
        two = requests.filtered(lambda r: 'Steel supply' in r.recording_demo_scenario)
        self.assertEqual(two.quotation_attachment_count, 2)
        self.assertEqual(two.quotation_status, 'remaining_1')
        uploaded = requests.filtered(lambda r: 'invoice uploaded, not submitted' in r.recording_demo_scenario)
        self.assertEqual(uploaded.accounting_docs_status, 'pending')
        self.assertEqual(uploaded._get_accounting_attachment_count(), 1)
        self.assertTrue(uploaded.has_unsubmitted_accounting_docs())
        extra = requests.filtered(lambda r: 'new document after submission' in r.recording_demo_scenario)
        self.assertEqual(extra._get_accounting_attachment_count(), 2)
        self.assertEqual(extra.accounting_docs_submitted_attachment_count, 1)
        self.assertTrue(extra.has_unsubmitted_accounting_docs())
        self.assertEqual(set(requests.mapped('accounting_docs_status')),
                         {'pending', 'submitted', 'received', 'need_more', 'processed', 'rejected'})

    def test_stages_and_project_routing(self):
        self.assertEqual(len(self.batch.employee_request_ids), 16)
        for request in self.batch.employee_request_ids | self.env['employee.request']:
            self.assertIn(request.project_id, request.employee_id._get_material_request_projects())
        for requests in (self.batch.employee_request_ids, self.batch.material_request_ids):
            for request in requests:
                self.assertIn(request.project_id, request.employee_id._get_material_request_projects())
                if request.state == 'workflow':
                    self.assertEqual(len(request.approval_line_ids.filtered(lambda l: l.state == 'pending')), 1)
                    self.assertTrue(request.current_approval_line_id)
                elif request.state == 'approved':
                    self.assertTrue(all(line.state == 'approved' for line in request.approval_line_ids))
                elif request.state == 'returned':
                    self.assertEqual(len(request.approval_line_ids.filtered(lambda l: l.state == 'returned')), 1)
        clarification = self.batch.material_request_ids.filtered('needs_clarification')
        self.assertEqual(len(clarification), 1)
        self.assertTrue(clarification.clarification_question)

    def test_repeat_and_permissions(self):
        ids = self.batch.material_request_ids.ids
        self.batch.action_create_samples()
        self.assertEqual(self.batch.material_request_ids.ids, ids)
        self.assertFalse(any(self.batch.employee_request_ids.mapped('employee_id.user_id')))
        with self.assertRaises(AccessError):
            self.batch.with_user(self.env.ref('base.public_user')).action_create_samples()

    def test_generator_never_provisions_accounts(self):
        batch = self.env['employee.portal.recording.demo'].with_user(self.admin).create({
            'name': 'No account provisioning regression', 'confirmed_demo': True,
            'include_draft_documents': False,
        })
        user_model = type(self.env['res.users'])
        with patch.object(user_model, 'create', side_effect=AssertionError('Must not create users')):
            with patch.object(user_model, 'write', side_effect=AssertionError('Must not change users')):
                batch.action_create_samples()
        self.assertEqual(len(batch.employee_request_ids), 16)
        self.assertEqual(len(batch.material_request_ids), 28)
        self.assertFalse(batch.employee_request_ids.mapped('employee_id.user_id'))
        self.assertTrue(all(line.approver_user_ids == self.admin for line in
                            batch.material_request_ids.approval_line_ids))

    def test_saved_setup_with_missing_approvers(self):
        batch = self.env['employee.portal.recording.demo'].with_user(self.admin).create({
            'name': 'Saved setup with empty upgrade fields', 'confirmed_demo': True,
            'include_draft_documents': False,
            'manager_user_id': False, 'hr_user_id': False, 'finance_user_id': False,
            'ceo_user_id': False, 'purchase_user_id': False, 'store_user_id': False,
            'project_manager_user_id': False, 'director_user_id': False,
        })
        user_model = type(self.env['res.users'])
        with patch.object(user_model, 'create', side_effect=AssertionError('Must not create users')):
            with patch.object(user_model, 'write', side_effect=AssertionError('Must not change users')):
                batch.action_create_samples()
        self.assertEqual(batch.state, 'ready')
        self.assertEqual(batch.manager_user_id, self.admin)
        self.assertEqual(len(batch.employee_request_ids), 16)
        self.assertEqual(len(batch.material_request_ids), 28)

    def test_inactive_saved_approver_is_repaired(self):
        batch = self.env['employee.portal.recording.demo'].with_user(self.admin).create({
            'name': 'Inactive migrated approver', 'manager_user_id': self.env.ref('base.user_root').id,
        })
        users = batch._resolve_demo_approvers()
        # In standard Odoo the root/OdooBot account is inactive. Whichever saved
        # user was selected, the resolved result must be active and company-valid.
        self.assertTrue(users['manager'].active)
        self.assertIn(batch.company_id, users['manager'].company_ids)
