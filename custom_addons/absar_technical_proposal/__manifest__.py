{
 'name': 'ABSAR Technical & Financial Proposals',
 'version': '18.0.1.0.0',
 'summary': 'Editable technical proposals, reusable sections, milestones and PDF from Sales Quotations',
 'category': 'Sales/Sales',
 'author': 'ABSAR Al Omran Construction Company',
 'license': 'LGPL-3',
 'depends': ['sale_management', 'construction_contract_management'],
 'data': [
  'security/ir.model.access.csv',
  'security/proposal_rules.xml',
  'views/proposal_template_views.xml',
  'views/sale_order_views.xml',
  'reports/proposal_report.xml',
 ],
 'application': False,
 'installable': True,
}
