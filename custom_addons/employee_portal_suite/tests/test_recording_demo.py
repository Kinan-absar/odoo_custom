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
        requester = self.batch.employee_request_ids[0].employee_id.user_id
        self.assertFalse(requester.has_group('base.group_user'))
        with self.assertRaises(AccessError):
            self.batch.with_user(requester).action_create_samples()
