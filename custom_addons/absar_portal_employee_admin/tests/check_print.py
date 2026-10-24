"""Actual print controller with ACL-sensitive report fixtures; no installed Odoo."""
from pathlib import Path
from types import SimpleNamespace as NS
import ast,unittest
class AccessError(Exception):pass
class UserError(Exception):pass
class NotFound(Exception):pass
ROOT=Path(__file__).resolve().parents[1]
class Report:
 def __init__(self,ident=5,model='hr.payslip',typ='qweb-pdf',sudo=False):self.id=ident;self._model=model;self._type=typ;self.privileged=sudo
 def sudo(self):return Report(self.id,self._model,self._type,True)
 @property
 def model(self):
  if not self.privileged:raise AccessError('Report Action ACL')
  return self._model
 @property
 def report_type(self):
  if not self.privileged:raise AccessError('Report Action ACL')
  return self._type
class ReportEnv:
 def __init__(self,report):self.report=report;self.rendered=[];self.refs=[]
 def ref(self,key,**kw):self.refs.append(key);return self.report
 def __getitem__(self,key):assert key=='ir.actions.report';return self
 def _render_qweb_pdf(self,report_id,res_ids):self.rendered.append((report_id,res_ids));return b'%PDF-fixture','pdf'
class Gateway:
 def __init__(self,env,company):self.env=env;self.company=company;self.block_record=False;self.block_company=False;self.env_calls=0;self.checked=[]
 def _company(self,ident):
  if self.block_company:raise AccessError('Company denied')
  return self.company
 def _record(self,company,kind,ident):
  self.checked.append((company.id,kind,ident))
  if self.block_record:raise AccessError('Payroll role / record denied')
  return NS(id=ident,name='Payslip')
 def _report_scope(self,c,r):self.scoped=(c.id,r.id)
 def _env(self,c):assert c==self.company;self.env_calls+=1;return self.env
source=ast.parse((ROOT/'controllers/portal.py').read_text());cls=next(c for c in source.body if isinstance(c,ast.ClassDef));fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='print_record');fn.decorator_list=[]
class Tests(unittest.TestCase):
 def setUp(self):
  self.company=NS(id=1,employee_admin_payslip_report_id=False);self.company.sudo=lambda:self.company
  self.env=ReportEnv(Report());self.s=Gateway(self.env,self.company)
  def no_direct_ref(*a,**k):raise AssertionError('Must not look up report metadata through the portal user env')
  self.request=NS(env=NS(ref=no_direct_ref),make_response=lambda pdf,headers:(pdf,dict(headers)))
  ns={'request':self.request,'UserError':UserError,'NotFound':NotFound,'_':lambda s:s,'content_disposition':lambda name:name}
  exec(compile(ast.Module(body=[fn],type_ignores=[]),'print-route','exec'),ns)
  self.call=lambda kind='payslips':ns['print_record'](NS(_service=lambda:self.s),kind,1200,company_id=1)
 def test_standard_report_acl_and_scoped_render(self):
  pdf,headers=self.call();self.assertTrue(pdf.startswith(b'%PDF'));self.assertEqual(self.env.refs,['hr_payroll.action_report_payslip']);self.assertEqual(self.env.rendered,[(5,[1200])]);self.assertEqual(self.s.checked,[(1,'payslips',1200)]);self.assertEqual(headers['Cache-Control'],'private, no-store')
 def test_custom_report_also_elevated_before_metadata(self):
  self.company.employee_admin_payslip_report_id=Report(17);self.call();self.assertFalse(self.env.refs);self.assertEqual(self.env.rendered,[(17,[1200])])
 def test_wrong_report_model_rejected(self):
  self.company.employee_admin_payslip_report_id=Report(17,'res.partner')
  with self.assertRaises(UserError):self.call()
  self.assertFalse(self.env.rendered)
 def test_company_and_payroll_denials_precede_report_access(self):
  self.s.block_company=True
  with self.assertRaises(AccessError):self.call()
  self.s.block_company=False;self.s.block_record=True
  with self.assertRaises(AccessError):self.call()
  self.assertFalse(self.s.env_calls);self.assertFalse(self.env.refs);self.assertFalse(self.env.rendered)
 def test_salary_report_uses_same_company_environment(self):
  self.env.report=Report(8,'employee.attendance.salary.report');self.call('salary-reports');self.assertEqual(self.s.scoped,(1,1200));self.assertEqual(self.env.refs,['employee_portal_suite.action_report_salary_summary']);self.assertEqual(self.env.rendered,[(8,[1200])])
if __name__=='__main__':unittest.main(verbosity=2)
