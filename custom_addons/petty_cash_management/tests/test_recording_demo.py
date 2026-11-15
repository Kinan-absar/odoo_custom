from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPettyCashRecordingDemo(AccountTestInvoicingCommon):
    def _new_demo(self):
        vals = {'company_id':self.env.company.id,'confirmed_demo':True,'include_posted':True}
        if 'include_portal' in self.env['petty.cash.recording.demo']._fields:vals['include_portal'] = False
        return self.env['petty.cash.recording.demo'].create(vals)

    def test_examples_totals_vouchers_and_idempotency(self):
        demo = self._new_demo()
        original_type = (self.env.ref('base.group_user') in self.env.user.groups_id,
                         self.env.ref('base.group_portal') in self.env.user.groups_id)
        users_before = self.env['res.users'].with_context(active_test=False).search_count([])
        demo.action_create_examples()
        reports = self.env['petty.cash'].search([('recording_demo_id','=',demo.id)])
        self.assertEqual(len(reports),12)
        self.assertEqual(len(reports.line_ids),36)
        self.assertEqual(set(reports.mapped('state')),{'draft','submitted','review_2','manager_approval','approved','refused'})
        self.assertEqual(len(reports.filtered(lambda r:r.state=='draft' and r.correction_reason)),2)
        for report in reports:
            self.assertAlmostEqual(report.amount_total,report.amount_untaxed+report.amount_vat,places=2)
        self.assertTrue(reports.filtered(lambda r:r.amount_vat>0))
        self.assertTrue(reports.filtered(lambda r:r.amount_vat==0))
        moves = reports.journal_entry_id
        self.assertEqual(len(moves),2)
        self.assertEqual(set(moves.mapped('state')),{'draft','posted'})
        for move in moves:
            self.assertAlmostEqual(sum(move.line_ids.mapped('balance')),0,places=2)
            self.assertEqual(move.petty_cash_report_id.journal_entry_id,move)
            self.assertTrue(self.env['ir.attachment'].search_count([('res_model','=','account.move'),('res_id','=',move.id)]))
        before = dict(demo.records_json)
        demo.action_create_examples()
        self.assertEqual(demo.records_json,before)
        self.assertEqual(self.env['petty.cash'].search_count([('recording_demo_id','=',demo.id)]),12)
        self.assertEqual(users_before,self.env['res.users'].with_context(active_test=False).search_count([]))
        self.assertEqual(original_type,(self.env.ref('base.group_user') in self.env.user.groups_id,
                                      self.env.ref('base.group_portal') in self.env.user.groups_id))

    def test_requires_opt_in(self):
        demo = self._new_demo();demo.confirmed_demo = False
        with self.assertRaises(UserError):demo.action_create_examples()
        self.assertFalse(demo.records_json)

    def test_builder_failure_rolls_back_everything(self):
        demo = self._new_demo()
        before = self.env['account.account'].search_count([])
        def fail_after_record(record):
            record.env['res.partner'].create({'name':'Recording rollback sentinel'})
            raise UserError('Injected fixture failure')
        with patch.object(type(demo),'_demo_build',fail_after_record):
            with self.assertRaises(UserError):demo.action_create_examples()
        self.assertFalse(self.env['res.partner'].search([('name','=','Recording rollback sentinel')]))
        self.assertEqual(before,self.env['account.account'].search_count([]))
        self.assertEqual(demo.state,'draft')

    def test_non_administrator_cannot_seed(self):
        user = self.env['res.users'].create({'name':'Demo security test','login':'petty.demo.security',
            'company_id':self.env.company.id,'company_ids':[Command.set(self.env.company.ids)],
            'groups_id':[Command.set([self.env.ref('base.group_user').id])]})
        with self.assertRaises(AccessError):self._new_demo().with_user(user).action_create_examples()
