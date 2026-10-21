{
 'name':'ABSAR Portal Sales', 'version':'18.0.1.4.5',
 'summary':'Employee Portal quotation and technical proposal preparation with review workflow',
 'author':'ABSAR Al Omran Construction Company','license':'LGPL-3',
 'category':'Sales/Sales','depends':['employee_portal_suite','sale_management','absar_technical_proposal','mail'],
 'data':['security/groups.xml','views/res_partner_views.xml','views/sale_customer_filter_views.xml','views/sale_order_views.xml','views/portal_sales_templates.xml','views/portal_navigation.xml','data/salesperson_sync.xml'],
 'assets':{'web.assets_frontend':['absar_portal_sales/static/src/record_cards.css','absar_portal_sales/static/src/record_rows.js','absar_portal_sales/static/src/css/portal_sales.css','absar_portal_sales/static/src/css/purchase_controls.css','absar_portal_sales/static/src/css/sales_lines.css','absar_portal_sales/static/src/js/purchase_ui.js','absar_portal_sales/static/src/js/analytic_editor.js','absar_portal_sales/static/src/js/portal_sales.js','absar_portal_sales/static/src/js/sales_lines.js']},
 'installable':True,'application':False,
}
