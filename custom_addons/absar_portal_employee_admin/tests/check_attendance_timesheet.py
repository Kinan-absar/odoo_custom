"""Run actual report authorization and date-selection code on ORM-shaped fixtures."""
import ast
import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path

import check_gateway as fixtures
from check_gateway import AccessError, ValidationError, Rec, Records, User, Env, Model, ADMIN, HR, PAY

fixtures.odoo.models.TransientModel = object
fixtures.odoo.fields.Html = lambda *a, **kw: None
fixtures.odoo.api = types.SimpleNamespace(onchange=lambda *args: lambda fn: fn, model=lambda fn: fn)
class DateField:
    to_date = staticmethod(fixtures.Dates.to_date)
    context_today = staticmethod(lambda self: date(2026, 10, 31))
    def __call__(self, *args, **kw): return None
fixtures.odoo.fields.Date = DateField()
spec = importlib.util.spec_from_file_location('timesheet', fixtures.ROOT / 'models/attendance_timesheet.py')
module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AttendanceModel(Model):
    def search(self, domain, **kw):
        self.queries.append(domain)
        def match(rec):
            for path, op, target in domain:
                value = fixtures.get(rec, path)
                if op == '=' and value != target: return False
                if op == '>=' and value < target: return False
                if op == '<' and value >= target: return False
            return True
        return Records(sorted((r for r in self.rows if match(r)), key=lambda r: (r.check_in, r.id)))

class Tests(unittest.TestCase):
    def setUp(self):
        self.company = Rec('res.company', 1)
        self.other_company = Rec('res.company', 2)
        self.user = User('res.users', 9, active=True, public=False, share=True, groups={ADMIN, HR},
                         company_id=self.company, company_ids=Records([self.company]), tz='Asia/Riyadh')
        self.env = Env(); self.env.user = self.user
        self.env['res.company'] = Model('res.company', self.env, rows=[self.company, self.other_company])
        self.employee = Rec('hr.employee', 3, company_id=self.company, name='Employee', active=False)
        self.foreign_employee = Rec('hr.employee', 4, company_id=self.other_company)
        self.env['hr.employee'] = Model('hr.employee', self.env, rows=[self.employee,self.foreign_employee])
        gateway = fixtures.gateway.EmployeeAdminGateway(); gateway.env = self.env
        self.env['absar.employee.admin.gateway'] = gateway
        self.attendance = AttendanceModel('hr.attendance', self.env, rows=[])
        self.env['hr.attendance'] = self.attendance
        self.service = module.AttendanceTimesheetService(); self.service.env = self.env
    def row(self, ident, check_in, check_out=None, hours=0, employee=None):
        rec = Rec('hr.attendance', ident, employee_id=employee or self.employee,
                  check_in=datetime.fromisoformat(check_in),
                  check_out=datetime.fromisoformat(check_out) if check_out else False, worked_hours=hours)
        self.attendance.rows.append(rec)
    def data(self, **kw):
        return self.service._data(kw.get('company',1),kw.get('employee',3),kw.get('start','2026-10-01'),kw.get('end','2026-10-02'))
    def test_regular_employee_cannot_print_even_own_attendance(self):
        self.user.groups = set()
        with self.assertRaises(AccessError): self.data()
        self.assertFalse(self.attendance.queries)
    def test_payroll_only_role_cannot_print(self):
        self.user.groups = {ADMIN, PAY}
        with self.assertRaises(AccessError): self.data()
    def test_portal_hr_group_alone_does_not_grant_access(self):
        self.user.groups = {HR}
        with self.assertRaises(AccessError): self.data()
    def test_internal_attendance_manager_can_print(self):
        self.user.share=False; self.user.groups={'hr_attendance.group_hr_attendance_manager'}
        self.assertEqual(self.data()['total_days'],2)
    def test_inactive_and_attendance_only_denied(self):
        self.user.active=False
        with self.assertRaises(AccessError): self.data()
        self.user.active=True;self.user.groups.add('employee_portal_suite.group_attendance_only')
        with self.assertRaises(AccessError):self.data()
    def test_foreign_company_and_employee_rejected(self):
        with self.assertRaises(AccessError): self.data(company=2)
        with self.assertRaises(AccessError): self.data(employee=4)
        self.assertFalse(self.attendance.queries)
    def test_dates_required_and_ordered(self):
        for kw in ({'start':''},{'end':''},{'start':'bad'},{'start':'2026-11-01'},{'employee':'bad'}):
            with self.assertRaises(ValidationError):self.data(**kw)
    def test_timezone_boundaries_multiple_shifts_native_hours(self):
        self.row(1,'2026-09-30 20:59:59','2026-09-30 21:30:00',0.5)
        self.row(2,'2026-09-30 21:00:00','2026-10-01 01:00:00',3.5)
        self.row(3,'2026-10-01 10:00:00','2026-10-01 12:00:00',2)
        self.row(4,'2026-10-02 21:00:00','2026-10-03 01:00:00',4)
        result=self.data()
        self.assertEqual(result['total_hours'],'5.50')
        self.assertEqual(result['rows'][0]['check_in'],'00:00')
        self.assertEqual(result['rows'][0]['date'],'01/10/2026')
        self.assertEqual(len(result['rows']),3)
        self.assertEqual(result['rows'][-1]['note'],'No attendance recorded')
    def test_overnight_kept_in_full_and_open_excluded(self):
        self.row(1,'2026-10-02 20:00:00','2026-10-03 04:00:00',7.5)
        self.row(2,'2026-10-02 10:00:00',None,99)
        result=self.data()
        self.assertEqual(result['total_hours'],'7.50')
        self.assertEqual(result['rows'][-1]['check_out'],'03/10/2026 07:00')
        self.assertIn('Open check-in',result['rows'][1]['note'])
    def test_dst_day_boundaries(self):
        self.user.tz='Europe/Berlin'
        self.row(1,'2026-10-24 22:00:00','2026-10-25 22:59:59',24)
        result=self.data(start='2026-10-25',end='2026-10-25')
        lower,upper=self.attendance.queries[-1][-2:]
        self.assertEqual((upper[2]-lower[2]).total_seconds()/3600,25)
        self.assertEqual(result['total_hours'],'24.00')
    def test_direct_report_path_rechecks_access(self):
        report=module.AttendanceTimesheetReport();report.env=self.env
        self.env['absar.attendance.timesheet.service']=self.service
        self.user.groups=set()
        with self.assertRaises(AccessError):report._get_report_values([3],{'company_id':1,'employee_id':3,'date_from':'2026-10-01','date_to':'2026-10-02'})
    def test_new_files_and_template_ids(self):
        from lxml import etree
        root=fixtures.ROOT
        for p in root.rglob('*.xml'):etree.parse(str(p))
        tree=etree.parse(str(root/'views/attendance_timesheet.xml'))
        self.assertEqual(len(tree.xpath('//record[@id="action_attendance_timesheet_pdf"]')),1)
        self.assertFalse(tree.xpath('//field[@name="binding_model_id"]'))
        baseline=ast.literal_eval((root/'__manifest__.py').read_text())
        self.assertIn('views/attendance_timesheet.xml',baseline['data'])

    def test_backend_menu_nested_and_preview_shares_pdf_body(self):
        from lxml import etree
        tree=etree.parse(str(fixtures.ROOT/'views/attendance_timesheet.xml'))
        menu=tree.xpath('//menuitem[@id="menu_attendance_timesheet_root"]')[0]
        self.assertEqual(menu.get('parent'),'hr_attendance.menu_hr_attendance_root')
        self.assertTrue(tree.xpath('//button[@name="action_preview"]'))
        self.assertTrue(tree.xpath('//template[@id="attendance_timesheet_pdf"]//t[@t-call="absar_portal_employee_admin.attendance_timesheet_body"]'))

    def test_backend_preview_and_clear_on_filter_change(self):
        rendered=[]
        class View:
            def sudo(self):return self
            def _render_template(self,name,values):
                rendered.append((name,values));return '<p>Preview</p>'
        self.env['absar.attendance.timesheet.service']=self.service
        self.env['ir.ui.view']=View()
        wizard=module.AttendanceTimesheetWizard();wizard.env=self.env
        wizard.ensure_one=lambda:None;wizard.id=8
        wizard.company_id=self.company;wizard.employee_id=self.employee
        wizard.date_from=date(2026,10,1);wizard.date_to=date(2026,10,2)
        action=wizard.action_preview()
        self.assertEqual(action['res_id'],8)
        self.assertEqual(wizard.preview_html,'<p>Preview</p>')
        self.assertEqual(rendered[0][0],'absar_portal_employee_admin.attendance_timesheet_body')
        wizard._onchange_preview_filters()
        self.assertFalse(wizard.preview_html)
        self.user.groups=set()
        with self.assertRaises(AccessError):wizard.action_preview()
        self.assertEqual(len(rendered),1)

if __name__=='__main__': unittest.main(verbosity=2)
