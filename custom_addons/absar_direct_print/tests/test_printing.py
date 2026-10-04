import json
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tests import tagged
from odoo.exceptions import AccessError, UserError

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
