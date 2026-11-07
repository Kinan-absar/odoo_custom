"""Optional real-registry notification tests. Run with --test-tags pbw_notifications.
Not executed in the offline packaging environment.
"""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged('-standard', '-at_install', 'post_install', 'pbw_notifications')
class TestWorkspaceNotifications(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        def portal(login, role):
            user = cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': login, 'login': login, 'email': login + '@example.invalid',
                'company_id': cls.company.id, 'company_ids': [Command.set([cls.company.id])],
                'groups_id': [Command.set([cls.env.ref('base.group_portal').id,
                                          cls.env.ref('portal_backend_workspace.' + role).id])],
            })
            cls.env['hr.employee'].create({'name': login, 'user_id': user.id, 'company_id': cls.company.id})
            return user
        cls.preparer = portal('pbw-notice-preparer', 'sales__group_portal_sales_creator')
        cls.approver = portal('pbw-notice-approver', 'sales__group_portal_sales_approver')
        cls.other = portal('pbw-notice-other', 'sales__group_portal_sales_creator')
        customer = cls.env['res.partner'].create({'name': 'Notification test customer'})
        cls.order = cls.env['sale.order'].sudo().create({
            'partner_id': customer.id, 'company_id': cls.company.id,
            'pbw_portal_creator_id': cls.preparer.id,
        })
        cls.service = cls.env['pbw.workspace.notification']

    def _emit(self, token='one'):
        self.service._emit(self.approver, self.order, 'sales', 'Review needed', 'Open the quotation.', event_token=token)
        return self.service.sudo().search([('user_id', '=', self.approver.id), ('resource_model', '=', 'sale.order'), ('resource_id', '=', self.order.id)])

    def test_persistent_delivery_and_idempotency(self):
        self._emit(); notices = self._emit()
        self.assertEqual(len(notices), 1)
        data = self.env['pbw.notification.seen'].with_user(self.approver)._get_bell_data(self.approver)
        self.assertEqual(data['workspace_unread_count'], 1)

    def test_recipient_only_read(self):
        notice = self._emit()
        with self.assertRaises(AccessError):
            self.service.with_user(self.other)._mark_read(self.other, notice.id)
        self.service.with_user(self.approver)._mark_read(self.approver, notice.id)
        self.assertTrue(notice.read_at)

    def test_zero_id_is_not_mark_all(self):
        notice = self._emit()
        with self.assertRaises(AccessError):
            self.service.with_user(self.approver)._mark_read(self.approver, 0)
        self.assertFalse(notice.read_at)

    def test_read_watermark_keeps_later_event(self):
        first = self._emit()
        self._emit(token='two')
        self.service.with_user(self.approver)._mark_read(self.approver, upto_id=first.id)
        remaining = self.service.with_user(self.approver)._unread_snapshot(self.approver)
        self.assertEqual(remaining['count'], 1)

    def test_role_revocation_removes_notification(self):
        self._emit()
        self.approver.write({'groups_id': [Command.set([self.env.ref('base.group_portal').id,
                                                       self.env.ref('portal_backend_workspace.group_workspace_access').id])]})
        self.assertFalse(self.service.with_user(self.approver)._visible_records(self.approver))

    def test_direct_notification_orm_read_is_not_granted(self):
        notice = self._emit()
        with self.assertRaises(AccessError):
            notice.with_user(self.approver).read(['title'])

    def test_own_action_does_not_notify_actor(self):
        self.service.with_user(self.approver)._emit(self.approver, self.order, 'sales', 'Self', 'Self action')
        self.assertFalse(self.service.sudo().search([('user_id', '=', self.approver.id), ('title', '=', 'Self')]))
