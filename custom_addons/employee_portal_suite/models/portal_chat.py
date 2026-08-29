from odoo import fields, models


class PortalChatThread(models.Model):
    _name = 'portal.chat.thread'
    _description = 'Employee Portal Chat'
    _inherit = ['mail.thread']
    _order = 'last_message_date desc, id desc'

    name = fields.Char(required=True, default='Conversation')
    participant_ids = fields.Many2many(
        'res.users', 'portal_chat_thread_user_rel', 'thread_id', 'user_id',
        string='Participants', required=True,
    )
    is_group = fields.Boolean(default=False)
    direct_key = fields.Char(index=True, copy=False)
    last_message_date = fields.Datetime(default=fields.Datetime.now, index=True)


class PortalChatRead(models.Model):
    _name = 'portal.chat.read'
    _description = 'Employee Portal Chat Read State'
    _rec_name = 'thread_id'

    thread_id = fields.Many2one('portal.chat.thread', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    last_read_at = fields.Datetime(default=fields.Datetime.now, index=True)

    _sql_constraints = [
        ('portal_chat_read_unique', 'unique(thread_id, user_id)', 'Only one read state is allowed per user and conversation.'),
    ]
