from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPettyCashPortalRecordingDemo(AccountTestInvoicingCommon):
    def test_portal_records_and_single_user_type(self):
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name':'Test existing portal owner','login':'petty.demo.portal',
            'company_id':self.env.company.id,'company_ids':[Command.set(self.env.company.ids)],
            'groups_id':[Command.set([self.env.ref('base.group_portal').id])]})
        demo = self.env['petty.cash.recording.demo'].create({'confirmed_demo':True,
            'company_id':self.env.company.id,'include_portal':True,'portal_user_id':user.id})
        demo.action_create_examples()
        reports = self.env['petty.cash'].search([('recording_demo_id','=',demo.id)])
        self.assertEqual(len(reports),24)
        self.assertEqual(len(reports.line_ids),72)
        self.assertEqual(reports.with_user(user).search_count([('recording_demo_id','=',demo.id)]),12)
        self.assertTrue(user.has_group('petty_cash_management.group_portal_petty_cash_user'))
        self.assertTrue(user.has_group('base.group_portal'))
        self.assertFalse(user.has_group('base.group_user'))
        self.assertEqual(self.env['petty.cash.user.config'].search_count([
            ('partner_id','=',user.partner_id.id),('company_id','=',self.env.company.id)]),1)

    def test_internal_account_is_not_converted_to_portal(self):
        demo = self.env['petty.cash.recording.demo'].create({'confirmed_demo':True,
            'company_id':self.env.company.id,'include_portal':True,'portal_user_id':self.env.user.id})
        with self.assertRaises(UserError):demo.action_create_examples()
        self.assertFalse(demo.records_json)
