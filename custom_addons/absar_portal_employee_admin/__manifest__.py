{
 'name':'ABSAR Employee Admin Portal', 'version':'18.0.1.0.13',
 'summary':'Company-scoped employee, attendance, contract and payroll administration in the employee portal',
 'author':'ABSAR', 'license':'LGPL-3', 'category':'Human Resources',
 'depends':['employee_portal_suite','hr_attendance','hr_payroll','hr_contract','hr_work_entry'],
 'data':['security/groups.xml','security/ir.model.access.csv','security/rules.xml','views/company.xml','views/portal.xml'],
 'assets':{'web.assets_frontend':['absar_portal_employee_admin/static/src/admin.css','absar_portal_employee_admin/static/src/admin.js','absar_portal_employee_admin/static/src/form_ui.js','absar_portal_employee_admin/static/src/batch.js']},
 'application':False,'installable':True,
}
