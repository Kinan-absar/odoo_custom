{
 'name':'Portal Backend Workspace',
 'version':'18.0.0.4.0',
 'category':'Website/Portal',
 'summary':'Independent Sales, Purchase, Accounting and HR workspaces for selected portal accounts',
 'license':'LGPL-3',
 'depends':['base','web','portal','website','mail','hr','hr_attendance','hr_contract','sale_management','purchase','account'],
 'data':['security/groups.xml','views/hr_employee_portal_user.xml','views/workspace.xml'],
 'assets':{'web.assets_frontend':['portal_backend_workspace/static/src/css/workspace.css']},
 'installable':True,'application':True,
}
