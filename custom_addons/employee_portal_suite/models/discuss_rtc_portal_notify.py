import logging

from odoo import models
from odoo.tools.image import image_data_uri

_logger = logging.getLogger(__name__)


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _rtc_invite_members(self, member_ids=None):
        """Mirror native Discuss RTC invitations to the portal shell and Telegram.

        Native Discuss remains authoritative for ringing/accept/reject.  This hook
        only adds the portal bus alert and an optional Telegram alert for employee
        users (internal or portal) who connected Telegram.
        """
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
                        'Incoming %s from %s' % (call_kind, caller.name or 'Employee'),
                        'Tap to open Chats and answer.',
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
                            'Incoming %s from %s' % (call_kind, caller.name or 'Employee'),
                            'Open Chats to answer.',
                            path=open_path,
                        )
                    except Exception:
                        # Telegram is fallback-only and must never interrupt native RTC.
                        _logger.exception(
                            'Failed to mirror native RTC invitation to Telegram for user %s',
                            user.id,
                        )
        return invited
