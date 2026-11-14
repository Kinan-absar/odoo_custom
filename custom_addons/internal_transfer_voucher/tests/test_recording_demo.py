from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestVoucherRecordingDemo(AccountTestInvoicingCommon):
    """Run with --test-tags /internal_transfer_voucher:TestVoucherRecordingDemo.

    Transactional: posted fixtures are rolled back after each test.
    """

    def _setup_record(self):
        return self.env['voucher.recording.demo'].create({
            'name': 'Test recording setup', 'company_id': self.env.company.id,
            'confirmed_demo': True,
        })

    def test_fixtures_and_repeat_click(self):
        demo = self._setup_record()
        users_before = self.env['res.users'].with_context(active_test=False).search_count([])
        groups_before = self.env.user.groups_id
        demo.action_create_examples()
        self.assertEqual(demo.state, 'ready')
        registry = demo.records_json
        self.assertEqual(len(registry['cash.plan.run']), 3)
        self.assertEqual(len(registry['account.payment.voucher']), 10)
        self.assertEqual(len(registry['account.receipt.voucher']), 6)
        runs = self.env['cash.plan.run'].browse(registry['cash.plan.run'])
        self.assertTrue(all(runs.mapped('line_ids')))
        self.assertTrue(all(run.line_ids for run in runs))
        lines = self.env['cash.plan.line'].browse(registry['cash.plan.line'])
        self.assertTrue({'supplier', 'expense', 'payroll', 'cash', 'transfer', 'loan',
                         'customer', 'revenue', 'other'} <= set(lines.mapped('transaction_type')))
        self.assertTrue({'pending', 'approved', 'adjusted', 'held', 'rejected'} <= set(lines.mapped('ceo_decision')))
        payments = self.env['account.payment.voucher'].browse(registry['account.payment.voucher'])
        receipts = self.env['account.receipt.voucher'].browse(registry['account.receipt.voucher'])
        self.assertEqual(set(payments.mapped('state')), {'draft', 'posted', 'cancel'})
        self.assertEqual(set(receipts.mapped('state')), {'draft', 'posted', 'cancel'})
        self.assertTrue(payments.filtered(lambda p: len(p.po_allocation_ids) == 2))
        self.assertTrue(payments.filtered('bill_reconciled'))
        self.assertTrue(receipts.filtered('invoice_reconciled'))
        review = self.env['cash.plan.review'].browse(registry['cash.plan.review'])
        self.assertTrue({'add', 'update', 'remove', 'review', 'keep', 'convert'} <= set(review.line_ids.mapped('agent_action')))
        for voucher in payments.filtered(lambda p: p.state == 'posted'):
            self.assertEqual(voucher.move_id.state, 'posted')
            self.assertAlmostEqual(sum(voucher.move_id.line_ids.mapped('balance')), 0, places=2)
        counts = {model: self.env[model].search_count([]) for model in registry}
        demo.action_create_examples()
        self.assertEqual(demo.records_json, registry)
        self.assertEqual(counts, {model: self.env[model].search_count([]) for model in registry})
        self.assertEqual(users_before, self.env['res.users'].with_context(active_test=False).search_count([]))
        self.assertEqual(groups_before, self.env.user.groups_id)

    def test_requires_explicit_demo_opt_in(self):
        demo = self._setup_record()
        demo.confirmed_demo = False
        with self.assertRaises(UserError):
            demo.action_create_examples()
        self.assertFalse(demo.records_json)
        self.assertEqual(demo.state, 'draft')

    def test_non_accounting_administrator_cannot_seed(self):
        user = self.env['res.users'].create({
            'name': 'Recording security test', 'login': 'recording.security.test',
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)],
            'groups_id': [Command.set([self.env.ref('base.group_user').id])],
        })
        demo = self._setup_record()
        with self.assertRaises(AccessError):
            demo.with_user(user).action_create_examples()

    def test_failed_build_rolls_back_new_records(self):
        demo = self._setup_record()
        marker = 'Recording rollback sentinel'

        def fail_after_creation(record):
            record.env['res.partner'].create({'name': marker})
            raise UserError('Injected fixture failure')

        with patch.object(type(demo), '_build_examples', fail_after_creation):
            with self.assertRaises(UserError):
                demo.action_create_examples()
        self.assertFalse(self.env['res.partner'].search([('name', '=', marker)]))
        demo.invalidate_recordset()
        self.assertEqual(demo.state, 'draft')
        self.assertFalse(demo.records_json)
