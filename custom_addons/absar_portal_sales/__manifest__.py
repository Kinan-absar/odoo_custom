{
 'name':'ABSAR Portal Sales', 'version':'18.0.1.2.5',
 'summary':'Employee Portal quotation and technical proposal preparation with review workflow',
 'author':'ABSAR Al Omran Construction Company','license':'LGPL-3',
 'category':'Sales/Sales','depends':['employee_portal_suite','sale_management','absar_technical_proposal','mail'],
 'data':['security/groups.xml','views/sale_order_views.xml','views/portal_sales_templates.xml','views/portal_navigation.xml'],
 'assets':{'web.assets_frontend':['absar_portal_sales/static/src/css/portal_sales.css','absar_portal_sales/static/src/js/portal_sales.js']},
 'installable':True,'application':False,
}
