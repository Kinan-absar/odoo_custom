"""Run with --test-tags /absar_portal_purchase_monitor on a staging clone.

These integration tests require the installed EPS/Enterprise dependency stack.
They are included, but were not run in the artifact-building environment.
"""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestNativePurchaseSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env['res.partner'].create({'name': 'Native portal security vendor', 'supplier_rank': 1, 'company_id': cls.company.id})
        cls.product = cls.env['product.product'].create({'name': 'Native portal security product', 'purchase_ok': True, 'company_id': cls.company.id})
        prefix = 'absar_portal_purchase_monitor.group_portal_purchase_'
        def employee(login, roles):
            user = new_test_user(cls.env, login=login, groups=','.join(['base.group_portal'] + [prefix + role for role in roles]),
                                 company_id=cls.company.id, company_ids=[Command.set([cls.company.id])])
            cls.env['hr.employee'].create({'name': login, 'user_id': user.id, 'company_id': cls.company.id})
            return user
        cls.preparer = employee('native_purchase_preparer', ['native', 'preparer'])
        cls.other = employee('native_purchase_other', ['native', 'preparer'])
        cls.reviewer = employee('native_purchase_reviewer', ['native', 'approver'])
        cls.no_opt_in = employee('native_purchase_no_opt_in', ['preparer'])

    def _rfq(self, actor=None):
        return self.env['purchase.order'].with_user(actor or self.preparer).create({
            'partner_id': self.vendor.id, 'company_id': self.company.id,
            'order_line': [Command.create({'product_id': self.product.id, 'name': self.product.name,
                'product_uom': self.product.uom_po_id.id, 'product_qty': 2, 'price_unit': 10,
                'date_planned': '2026-12-01 10:00:00'})],
        })

    def test_portal_identity_and_opt_in(self):
        self.assertTrue(self.preparer.share)
        self.assertFalse(self.preparer.has_group('base.group_user'))
        with self.assertRaises(AccessError):
            self._rfq(self.no_opt_in)

    def test_no_cross_owner_read_or_edit(self):
        po = self._rfq()
        with self.assertRaises(AccessError):
            po.with_user(self.other).read(['name'])
        with self.assertRaises(AccessError):
            po.with_user(self.other).write({'partner_ref': 'tampered'})
        with self.assertRaises(AccessError):
            po.order_line.with_user(self.other).write({'price_unit': 0})

    def test_no_rpc_state_or_owner_injection(self):
        po = self._rfq()
        for vals in [{'state': 'purchase'}, {'absar_portal_preparer_id': self.other.id},
                     {'absar_portal_review_state': 'approved'}]:
            with self.assertRaises(AccessError):
                po.write(vals)
        with self.assertRaises(AccessError):
            po.with_context(absar_native_sent=True).write({'state': 'sent'})

    def test_approval_never_confirms_or_allows_content_edit(self):
        po = self._rfq()
        po.action_absar_portal_submit()
        with self.assertRaises((AccessError, UserError)):
            po.action_absar_portal_approve()
        po.with_user(self.reviewer).action_absar_portal_approve()
        self.assertEqual(po.state, 'draft')
        self.assertEqual(po.absar_portal_review_state, 'approved')
        with self.assertRaises(AccessError):
            po.write({'partner_ref': 'after approval'})
        with self.assertRaises(AccessError):
            po.button_confirm()

    def test_review_role_cannot_create_or_modify_products(self):
        with self.assertRaises(AccessError):
            self._rfq(self.reviewer)
        with self.assertRaises(AccessError):
            self.env['product.product'].with_user(self.preparer).create({'name': 'No product creation role'})

    def test_native_print_marks_own_draft_sent(self):
        po = self._rfq()
        action = po.print_quotation()
        self.assertEqual(po.state, 'sent')
        self.assertEqual(action['type'], 'ir.actions.report')
