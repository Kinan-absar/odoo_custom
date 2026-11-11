"""Optional real Odoo 18 registry tests, not executed during offline packaging.
Run on a disposable database with --test-tags pbw_sales_policy.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('-standard', '-at_install', 'post_install', 'pbw_sales_policy')
class TestSalesPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        def portal(login, role):
            user = cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'email': login + '@example.invalid',
                'company_id': cls.company.id,
                'company_ids': [Command.set(cls.company.ids)],
                'groups_id': [Command.set([
                    cls.env.ref('base.group_portal').id,
                    cls.env.ref('portal_backend_workspace.sales__group_portal_sales_' + role).id,
                ])],
            })
            cls.env['hr.employee'].create({
                'name': login, 'user_id': user.id, 'company_id': cls.company.id,
            })
            return user
        cls.preparer = portal('pbw-sales-test-preparer', 'creator')
        cls.operator = portal('pbw-sales-test-all-documents', 'user')
        cls.approver = portal('pbw-sales-test-approver', 'approver')
        cls.customer = cls.env['res.partner'].create({
            'name': 'Workspace sales policy customer', 'absar_is_sales_customer': True,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Workspace sales policy service', 'type': 'service', 'list_price': 10,
        })

    def order(self, creator):
        # sudo preserves the acting UID; never fabricate ownership in test values.
        return self.env['sale.order'].with_user(creator).sudo().create({
            'partner_id': self.customer.id, 'company_id': self.company.id,
            'order_line': [Command.create({
                'product_id': self.product.id, 'name': self.product.name,
                'product_uom': self.product.uom_id.id, 'product_uom_qty': 1,
                'price_unit': 10, 'tax_id': [Command.clear()],
            })],
        })

    def test_all_documents_cannot_submit_other_creator(self):
        order = self.order(self.preparer).with_user(self.operator).sudo()
        self.assertFalse(order._pbw_review_permissions(self.operator)['can_submit'])
        with self.assertRaises(UserError):
            order._pbw_portal_submit()
        self.assertEqual(order.create_uid, self.preparer)
        self.assertEqual(order.pbw_portal_review_state, 'draft')

    def test_approver_directly_confirms_own_order(self):
        order = self.order(self.approver)
        order._pbw_confirm_own_quotation()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.pbw_order_review_state, 'direct')
        self.assertEqual(order.pbw_direct_confirmed_by_id, self.approver)
        self.assertFalse(order.pbw_portal_approver_id)
        with self.assertRaises(AccessError):
            order._pbw_confirm_own_quotation()

    def test_approver_cannot_directly_confirm_other_creator(self):
        order = self.order(self.preparer).with_user(self.approver).sudo()
        with self.assertRaises(AccessError):
            order._pbw_confirm_own_quotation()
        self.assertEqual(order.state, 'draft')

    def test_native_confirm_does_not_bypass_preparer_review(self):
        order = self.order(self.preparer)
        with self.assertRaises(UserError):
            order.action_confirm()
        self.assertEqual(order.state, 'draft')

    def test_creator_not_changed_by_editor_enrollment(self):
        order = self.order(self.preparer).with_user(self.operator).sudo()
        order._pbw_review_write({'pbw_portal_creator_id': self.operator.id})
        self.assertEqual(order._pbw_sales_owner(), self.preparer)
        with self.assertRaises(UserError):
            order._pbw_portal_submit()

    def test_customer_flag_is_required_in_standalone_domain(self):
        unmarked = self.env['res.partner'].create({'name': 'Unmarked workspace contact'})
        domain = self.env['res.partner']._pbw_sales_customer_domain(self.company)
        eligible = self.env['res.partner'].search(domain)
        self.assertIn(self.customer, eligible)
        self.assertNotIn(unmarked, eligible)
