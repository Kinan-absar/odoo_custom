from odoo import fields, models, _

PREFIX = 'portal_backend_workspace.'
AREAS = (
    ('sales', 'Sales', 'fa-line-chart', ('sales__group_portal_sales_creator', 'sales__group_portal_sales_approver', 'sales__group_portal_sales_monitor', 'sales__group_portal_sales_user')),
    ('purchase', 'Purchase', 'fa-shopping-cart', ('purchase__group_portal_purchase_preparer', 'purchase__group_portal_purchase_approver', 'purchase__group_portal_purchase_monitor', 'purchase__group_portal_purchase_user')),
    ('accounting', 'Accounting', 'fa-calculator', ('accounting__group_accountant', 'accounting__group_preparer', 'accounting__group_approver', 'accounting__group_monitor', 'accounting__group_customer_invoicing')),
    ('hr', 'HR Administration', 'fa-users', ('hr__group_employee_admin', 'hr__group_payroll_admin')),
)

class WorkspaceUser(models.Model):
    _inherit = 'res.users'

    def _pbw_has_access(self):
        self.ensure_one()
        return self.active and not self._is_public() and self.has_group(PREFIX + 'group_workspace_access')

    def _pbw_landing_url(self):
        """Optional integration bridges can choose a different neutral landing page."""
        self.ensure_one()
        return '/my/workspace' if self._pbw_has_access() else False

    def _pbw_extra_navigation(self):
        """No cross-product links in the base addon. Extended only by bridges."""
        self.ensure_one()
        return []

    def _pbw_workspace_areas(self):
        self.ensure_one()
        if not self._pbw_has_access():
            return []
        result = []
        for key, label, icon, groups in AREAS:
            if not any(self.has_group(PREFIX + group) for group in groups):
                continue
            links = []
            if key == 'sales':
                sales_url = '/my/workspace/sales' if any(self.has_group(PREFIX+'sales__'+g) for g in ('group_portal_sales_creator','group_portal_sales_user','group_portal_sales_approver')) else '/my/workspace/sales/monitor'
                links.append(('Quotations & Orders', sales_url, 'fa-file-text-o'))
                if self.has_group(PREFIX + 'sales__group_portal_sales_approver'):
                    links.append(('Sales Approvals', '/my/workspace/sales/approvals', 'fa-check-square-o'))
                if self.has_group(PREFIX + 'sales__group_portal_sales_creator'):
                    links.append(('Review Updates', '/my/workspace/sales/updates', 'fa-bell-o'))
            elif key == 'purchase':
                purchase_url = '/my/workspace/purchase' if any(self.has_group(PREFIX+'purchase__'+g) for g in ('group_portal_purchase_preparer','group_portal_purchase_user','group_portal_purchase_approver')) else '/my/workspace/purchase-monitor'
                links.append(('Purchase Orders', purchase_url, 'fa-shopping-cart'))
                if self.has_group(PREFIX + 'purchase__group_portal_purchase_approver'):
                    links.append(('Purchase Approvals', '/my/workspace/purchase/approvals', 'fa-check-square-o'))
                
                if self.has_group(PREFIX+'purchase__group_portal_purchase_preparer'):
                    links.append(('Products', '/my/workspace/purchase/products', 'fa-cubes'))
                if self.has_group(PREFIX+'purchase__group_portal_purchase_monitor'):
                    links.append(('Purchase Monitoring', '/my/workspace/purchase-monitor', 'fa-eye'))
            elif key == 'accounting':
                links.append(('Accounting Dashboard', '/my/workspace/accounting', 'fa-calculator'))
                if self.has_group(PREFIX + 'accounting__group_customer_invoicing'):
                    links.append(('Customer Invoices', '/my/workspace/accounting/invoices', 'fa-file-text-o'))
                if any(self.has_group(PREFIX + 'accounting__group_' + g) for g in ('accountant', 'preparer', 'approver', 'monitor')):
                    links += [('Vendor Bills', '/my/workspace/accounting/bills', 'fa-file-text-o'), ('Journal Entries', '/my/workspace/accounting/journals', 'fa-book')]
            elif key == 'hr':
                if self.has_group(PREFIX + 'hr__group_employee_admin'):
                    links += [('Employees', '/my/workspace/hr/employees', 'fa-users'), ('Attendance', '/my/workspace/hr/attendance', 'fa-clock-o')]
                if self.has_group(PREFIX + 'hr__group_payroll_admin'):
                    links += [('Contracts', '/my/workspace/hr/contracts', 'fa-file-text-o'), ('Work Entries', '/my/workspace/hr/work-entries', 'fa-calendar'), ('Payslips', '/my/workspace/hr/payslips', 'fa-money'), ('Payroll Batches', '/my/workspace/hr/batches', 'fa-folder-o')]
            result.append({'key': key, 'name': _(label), 'icon': icon, 'url': links[0][1] if links else '/my/workspace/' + key, 'links': links})
        return result

class WorkspaceEmployee(models.Model):
    _inherit = 'hr.employee'
    # Allow explicitly linked portal accounts; this grants no backend HR ACLs.
    user_id = fields.Many2one(domain="[('active', '=', True), ('company_ids', 'in', company_id)]")

class WorkspaceSaleOrder(models.Model):
    _inherit = 'sale.order'
    pbw_project_id = fields.Many2one('project.project', string='Workspace Project', check_company=True, copy=False)
