import logging

from odoo import _, models
from odoo.tools.image import image_data_uri
from odoo.exceptions import AccessError
from odoo.osv import expression

_logger = logging.getLogger(__name__)


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _portal_read_only_channel(self):
        self.ensure_one()
        channel = self.channel_id
        return bool(
            channel.channel_type == 'channel'
            and channel.employee_portal_access == 'read_only'
            and channel._is_employee_portal_user(self.env.user)
        )

    def _rtc_join_call(self, store=None, check_rtc_session_ids=None, camera=False):
        self.ensure_one()
        if self._portal_read_only_channel():
            raise AccessError(_('Audio and video calls are disabled for read-only portal Channels.'))
        return super()._rtc_join_call(
            store=store, check_rtc_session_ids=check_rtc_session_ids, camera=camera
        )

    def _get_rtc_invite_members_domain(self, member_ids=None):
        domain = super()._get_rtc_invite_members_domain(member_ids=member_ids)
        self.ensure_one()
        channel = self.channel_id
        if channel.channel_type == 'channel' and channel.employee_portal_access == 'read_only':
            portal_partner_ids = channel._employee_portal_candidate_users().partner_id.ids
            if portal_partner_ids:
                domain = expression.AND([domain, [('partner_id', 'not in', portal_partner_ids)]])
        return domain

    def _rtc_invite_members(self, member_ids=None):
        """Mirror native Discuss RTC invitations to the portal shell and Telegram.

        Native Discuss remains authoritative for ringing/accept/reject.  This hook
        only adds the portal bus alert and an optional Telegram alert for employee
        users (internal or portal) who connected Telegram.
        """
        for current in self:
            if current._portal_read_only_channel():
                raise AccessError(_('Audio and video calls are disabled for read-only portal Channels.'))
        invited = super()._rtc_invite_members(member_ids=member_ids)
        Employee = self.env['hr.employee'].sudo()
        Telegram = self.env['employee.portal.telegram.service'].sudo()
        WebPush = self.env['employee.portal.webpush.service'].sudo()

        for member in invited:
            employee_users = member.partner_id.user_ids.filtered(
                lambda user: user.active and Employee.search_count([
                    ('user_id', '=', user.id),
                    ('active', '=', True),
                ])
            )
            if not employee_users:
                continue

            channel = member.channel_id
            # The Chats PWA exposes employee conversations only.  Keep the extra
            # portal bus alert scoped to those channels while Telegram can notify
            # either internal or portal employee recipients.
            is_employee_chat = (
                'is_employee_portal_channel' not in channel._fields
                or channel.is_employee_portal_channel
            )
            if not is_employee_chat:
                continue

            session = member.rtc_inviting_session_id
            caller = session.channel_member_id.partner_id if session else self.partner_id
            is_video = bool(session and session.is_camera_on)
            open_path = '/my/employee/discuss?open_channel=%s' % channel.id

            # Portal shell companion event.  Native Discuss still owns the call.
            member._bus_send('employee_portal.native_rtc_invitation', {
                'channel_id': channel.id,
                'caller_name': caller.name or channel.display_name,
                'caller_avatar': image_data_uri(caller.avatar_128) if caller.avatar_128 else False,
                'is_video': is_video,
                'open_url': open_path,
            })

            call_kind = 'video call' if is_video else 'call'
            push_kind = 'video_call' if is_video else 'call'
            for user in employee_users:
                pushed = False
                try:
                    pushed = WebPush.send_to_user(
                        user,
                        caller.name or 'Employee',
                        ('Incoming video call. Tap to open Chats and answer.' if is_video else 'Incoming call. Tap to open Chats and answer.'),
                        path=open_path,
                        kind=push_kind,
                        tag='employee-chats-call-%s' % channel.id,
                        urgency='high',
                    )
                except Exception:
                    _logger.exception(
                        'Failed to send native Web Push RTC invitation for user %s', user.id
                    )
                if not pushed:
                    try:
                        Telegram.with_context(skip_webpush=True).send_to_user(
                            user,
                            caller.name or 'Employee',
                            ('Incoming video call. Open Chats to answer.' if is_video else 'Incoming call. Open Chats to answer.'),
                            path=open_path,
                        )
                    except Exception:
                        # Telegram is fallback-only and must never interrupt native RTC.
                        _logger.exception(
                            'Failed to mirror native RTC invitation to Telegram for user %s',
                            user.id,
                        )
        return invited
