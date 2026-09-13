# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools import html2plaintext
from odoo.tools.image import image_data_uri

class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _get_absar_chat_info(self, current_partner):
        """
        Format channel information specifically for the Absar Chat PWA client.
        Avoids N+1 queries by prefetching required data.
        """
        self.ensure_one()
        current_partner_id = current_partner.id

        # Determine display name and avatar
        other_members = self.channel_member_ids.filtered(lambda m: m.partner_id.id != current_partner_id)
        if self.channel_type == 'chat' and other_members:
            other_partner = other_members[0].partner_id
            name = other_partner.name
            avatar_url = image_data_uri(other_partner.sudo().avatar_128) if other_partner.sudo().avatar_128 else "/web/static/img/avatar.png"
            partner_id = other_partner.id
            is_direct = True
        else:
            name = self.name or (", ".join(self.channel_member_ids.mapped('partner_id.name')) or "Group Chat")
            avatar_url = "/web/static/img/avatar.png"
            partner_id = False
            is_direct = False

        # Find current user membership to compute unread count
        member = self.channel_member_ids.filtered(lambda m: m.partner_id.id == current_partner_id)
        seen_message_id = member.seen_message_id.id if member and member.seen_message_id else 0

        # Last message info. Query explicitly by descending id so previews are stable
        # regardless of the one2many cache/order used by mail.thread.
        last_message = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', self.id),
            ('message_type', '!=', 'user_notification'),
        ], order='id desc', limit=1)
        last_message_info = None
        unread_count = 0

        if last_message:
            plain_body = html2plaintext(last_message.body or "").strip()
            # truncate preview
            if len(plain_body) > 60:
                plain_body = plain_body[:57] + "..."
            
            last_message_info = {
                'id': last_message.id,
                'body': plain_body or ("Attachment" if last_message.attachment_ids else ""),
                'date': fields.Datetime.to_string(last_message.date),
                'author_id': last_message.author_id.id,
                'author_name': last_message.author_id.name or "System",
            }

            # Unread count computation: Reuse native Odoo Discuss member metadata
            # Completely avoids executing search_count() per channel in a loop (N+1 query)
            if member:
                if hasattr(member, 'message_unread_counter') and member.message_unread_counter is not None:
                    unread_count = member.message_unread_counter
                elif seen_message_id:
                    # Fast check: if latest message has already been seen or authored by current partner
                    if seen_message_id >= last_message.id or last_message.author_id.id == current_partner_id:
                        unread_count = 0
                    else:
                        unread_count = 1
                else:
                    unread_count = 1 if last_message.author_id.id != current_partner_id else 0

        return {
            'id': self.id,
            'name': name,
            'channel_type': self.channel_type,
            'is_direct': is_direct,
            'partner_id': partner_id,
            'avatar_url': avatar_url,
            'unread_count': unread_count,
            'last_message': last_message_info,
        }

    def _get_absar_messages_data(self, current_partner, limit=50, before_id=None):
        """
        Fetch paginated messages for Absar Chat timeline with strict participant validation.
        """
        self.ensure_one()
        current_partner_id = current_partner.id

        # Verify membership
        if current_partner_id not in self.channel_member_ids.mapped('partner_id.id'):
            return []

        domain = [
            ('res_id', '=', self.id),
            ('model', '=', 'discuss.channel'),
            ('message_type', '!=', 'user_notification'),
        ]
        if before_id:
            domain.append(('id', '<', int(before_id)))

        messages = self.env['mail.message'].sudo().search(
            domain,
            limit=limit,
            order='id desc'
        )

        result = []
        for msg in reversed(messages):
            result.append({
                'id': msg.id,
                'author_id': msg.author_id.id if msg.author_id else False,
                'author_name': msg.author_id.name if msg.author_id else (msg.email_from or "System"),
                'author_avatar': image_data_uri(msg.author_id.sudo().avatar_128) if msg.author_id and msg.author_id.sudo().avatar_128 else "/web/static/img/avatar.png",
                'body': msg.body or "",
                'date': fields.Datetime.to_string(msg.date),
                'is_current_user': bool(msg.author_id and msg.author_id.id == current_partner_id),
                'parent_id': msg.parent_id.id if msg.parent_id else False,
                'attachment_ids': [{
                    'id': att.id,
                    'name': att.name,
                    'mimetype': att.mimetype,
                    'file_size': att.file_size,
                    'url': f"/web/content/{att.id}?download=true",
                } for att in msg.attachment_ids],
            })

        return result
