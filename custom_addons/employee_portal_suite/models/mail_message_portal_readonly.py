from odoo import _, api, models
from odoo.exceptions import AccessError


def _is_read_only_portal_message(message, user):
    if not message or message.model != 'discuss.channel' or not message.res_id:
        return False
    channel = message.env['discuss.channel'].sudo().browse(message.res_id).exists()
    return bool(channel and channel._portal_channel_is_read_only_for(user))


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def write(self, vals):
        if any(_is_read_only_portal_message(message, self.env.user) for message in self):
            raise AccessError(_('This Channel is read-only in the Employee Portal.'))
        return super().write(vals)

    def unlink(self):
        if any(_is_read_only_portal_message(message, self.env.user) for message in self):
            raise AccessError(_('This Channel is read-only in the Employee Portal.'))
        return super().unlink()


class MailMessageReaction(models.Model):
    _inherit = 'mail.message.reaction'

    @api.model_create_multi
    def create(self, vals_list):
        messages = self.env['mail.message'].sudo().browse([
            vals.get('message_id') for vals in vals_list if vals.get('message_id')
        ]).exists()
        if any(_is_read_only_portal_message(message, self.env.user) for message in messages):
            raise AccessError(_('Reactions are disabled for read-only portal Channels.'))
        return super().create(vals_list)

    def unlink(self):
        if any(_is_read_only_portal_message(reaction.message_id, self.env.user) for reaction in self):
            raise AccessError(_('Reactions are disabled for read-only portal Channels.'))
        return super().unlink()
