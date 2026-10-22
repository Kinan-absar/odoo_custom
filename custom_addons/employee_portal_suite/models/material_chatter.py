"""Shared MR conversation and in-app notifications for portal and backend."""
from markupsafe import Markup
from odoo import api, models, _
from odoo.exceptions import AccessError, UserError


class MaterialRequestChatter(models.Model):
    _inherit = 'material.request'

    def _mr_conversation_users(self):
        self.ensure_one()
        users = self.employee_id.user_id
        if self.state == 'workflow' and self.current_approval_line_id:
            users |= self.current_approval_line_id.sudo()._effective_users()
        else:
            # Use the same legacy role/project checks as the approval form.
            users |= self.env['res.users'].sudo().search([
                ('active', '=', True), ('company_ids', 'in', self.employee_id.company_id.ids),
            ]).filtered(lambda user: self._portal_can_approve(user))
        reviewer = self.clarification_requested_by
        if reviewer and reviewer.active and self._portal_can_view(reviewer):
            users |= reviewer
        return users.filtered('active')

    def message_post(self, **kwargs):
        # Public Send Message comments in either UI alert the same participants.
        # Internal Log Notes and ordinary workflow tracking keep their native routing.
        public_comment = (
            kwargs.get('message_type') == 'comment'
            and (kwargs.get('subtype_xmlid') == 'mail.mt_comment'
                 or kwargs.get('subtype_id') == self.env.ref('mail.mt_comment').id)
            and not kwargs.get('is_internal')
        )
        if not public_comment:
            return super().message_post(**kwargs)
        self.ensure_one()
        partner_ids = set(kwargs.get('partner_ids') or [])
        if not self.env.context.get('eps_mr_explicit_recipients'):
            partner_ids.update(self._mr_conversation_users().partner_id.ids)
        kwargs['partner_ids'] = sorted(partner_ids)
        thread = self.with_context(eps_mr_inbox_partner_ids=sorted(partner_ids))
        return super(MaterialRequestChatter, thread).message_post(**kwargs)

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        recipients = super()._notify_get_recipients(message, msg_vals, **kwargs)
        inbox_ids = set(self.env.context.get('eps_mr_inbox_partner_ids') or [])
        # Use Odoo 18's native inbox pipeline (notification rows + bus Store update).
        # No preference changes, custom bus payloads or duplicate notification rows.
        return [dict(row, notif='inbox') if row['id'] in inbox_ids and row.get('uid') else row
                for row in recipients]

    def _portal_conversation_allowed(self, user):
        self.ensure_one()
        return self.employee_id.user_id == user or self._portal_can_view(user)

    def _portal_chatter_context(self, user, before=None):
        self.ensure_one()
        if not self._portal_conversation_allowed(user):
            raise AccessError(_('You cannot view this Material Request conversation.'))
        domain = [
            ('model', '=', 'material.request'), ('res_id', '=', self.id),
            ('message_type', 'in', ('comment', 'notification')),
            ('is_internal', '=', False), ('subtype_id', '!=', False),
            ('subtype_id.internal', '=', False),
        ]
        try:
            before_id = int(before or 0)
        except (ValueError, TypeError):
            before_id = 0
        if before_id > 0:
            domain.append(('id', '<', before_id))
        rows = self.env['mail.message'].sudo().search(domain, order='id desc', limit=51)
        messages = rows[:50]
        # Acknowledge only the displayed snapshot, only for the signed-in recipient.
        messages.with_user(user).sudo().set_message_done()
        return {'mr_messages': messages, 'mr_more_before': messages[-1].id if len(rows) > 50 else False}

    def _post_portal_chatter_message(self, text, mode='comment'):
        self.ensure_one()
        user = self.env.user
        if not self._portal_conversation_allowed(user):
            raise AccessError(_('You cannot post on this Material Request.'))
        text = (text or '').strip()
        if not text:
            raise UserError(_('Write a message before sending.'))
        if mode == 'reply':
            # A second click cannot turn an already answered question into a comment.
            return self._reply_clarification(text)
        if mode != 'comment':
            raise UserError(_('Invalid conversation action.'))
        self.sudo().message_post(
            body=Markup('<p style="white-space:pre-wrap">%s</p>') % text,
            message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=user.partner_id.id,
        )
        return True

    @api.model
    def _portal_mr_unread(self, user):
        notifications = self.env['mail.notification'].sudo().search([
            ('res_partner_id', '=', user.partner_id.id), ('is_read', '=', False),
            ('notification_type', '=', 'inbox'),
            ('mail_message_id.model', '=', 'material.request'),
            ('mail_message_id.is_internal', '=', False),
            ('mail_message_id.subtype_id', '!=', False),
            ('mail_message_id.subtype_id.internal', '=', False),
        ], order='id desc')
        records = self.sudo().browse(notifications.mail_message_id.mapped('res_id')).exists()
        visible = records.filtered(lambda rec: rec._portal_conversation_allowed(user))
        return notifications.filtered(lambda notification: notification.mail_message_id.res_id in visible.ids)


class MaterialChatterNotificationSummary(models.Model):
    _inherit = 'portal.report.seen'

    @api.model
    def _get_notification_summary(self, user):
        summary = super()._get_notification_summary(user)
        count = len(self.env['material.request']._portal_mr_unread(user))
        if count:
            summary['mr_message'] = {
                'count': count, 'new': count,
                'url': '/my/employee/material/notifications', 'label': _('Material Request messages'),
            }
        return summary
