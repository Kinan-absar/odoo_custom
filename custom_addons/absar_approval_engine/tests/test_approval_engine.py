from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAbsarApprovalEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group = cls.env.ref('absar_approval_engine.group_approval_user')
        cls.approver = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Approval Test User',
            'login': 'approval_test_user',
            'email': 'approval@example.com',
            'group_ids': [(6, 0, [group.id])],
        })
        model = cls.env['ir.model']._get('res.partner')
        cls.workflow = cls.env['absar.approval.workflow'].create({
            'name': 'Partner Test Approval',
            'model_id': model.id,
            'domain': '[]',
            'requester_can_approve': False,
            'stage_ids': [(0, 0, {
                'name': 'Review',
                'approver_source': 'users',
                'user_ids': [(6, 0, [cls.approver.id])],
                'approval_mode': 'any',
            })],
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Approval Test Partner'})

    def test_full_approval(self):
        request = self.env['absar.approval.request'].create_for_record(self.partner, self.workflow)
        self.assertEqual(request.state, 'in_progress')
        self.assertEqual(request.current_approver_ids, self.approver)
        request.with_user(self.approver).action_approve(comment='Approved')
        self.assertEqual(request.state, 'approved')
        self.assertTrue(request.completed_at)
        self.assertIn('approved', request.audit_ids.mapped('action'))

    def test_non_approver_cannot_approve(self):
        request = self.env['absar.approval.request'].create_for_record(self.partner, self.workflow)
        with self.assertRaises(Exception):
            request.action_approve()
