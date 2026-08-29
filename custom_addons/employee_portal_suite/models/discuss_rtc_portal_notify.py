from odoo import models
from odoo.tools.image import image_data_uri


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    def _rtc_invite_members(self, member_ids=None):
        """Keep Odoo RTC authoritative and mirror its invitation to portal shell.

        Odoo first creates the normal rtc_inviting_session_id and sends its
        native Store bus update.  We then send a tiny companion event on the
        exact same member personal bus so Employee Portal pages can surface
        the ringing call without loading the full Discuss/RTC frontend.
        """
        invited = super()._rtc_invite_members(member_ids=member_ids)
        for member in invited:
            user = member.partner_id.user_ids.filtered(lambda u: u.active and u.share)[:1]
            if not user or not self.env['hr.employee'].sudo().search_count([
                ('user_id', '=', user.id), ('active', '=', True)
            ]):
                continue
            channel = member.channel_id
            if 'is_employee_portal_channel' in channel._fields and not channel.is_employee_portal_channel:
                continue
            session = member.rtc_inviting_session_id
            caller = session.channel_member_id.partner_id if session else self.partner_id
            member._bus_send('employee_portal.native_rtc_invitation', {
                'channel_id': channel.id,
                'caller_name': caller.name or channel.display_name,
                'caller_avatar': image_data_uri(caller.avatar_128) if caller.avatar_128 else False,
                'is_video': bool(session and session.is_camera_on),
                'open_url': '/my/employee/discuss/channel/%s' % channel.id,
            })
        return invited
