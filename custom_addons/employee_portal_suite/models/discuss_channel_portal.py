from odoo import fields, models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    is_employee_portal_channel = fields.Boolean(
        string='Employee Portal Conversation', default=False, copy=False, index=True,
        help='Technical marker: this Discuss conversation is exposed in the Employee Portal.',
    )
    employee_portal_thread_id = fields.Many2one(
        'portal.chat.thread', string='Employee Portal Conversation', copy=False,
        ondelete='set null', index=True,
    )


class DiscussChannelMember(models.Model):
    _inherit = 'discuss.channel.member'

    # Portal frontend does not consume the native mail Store, so keep a tiny
    # persisted typing heartbeat while also calling native _notify_typing().
    portal_is_typing = fields.Boolean(default=False, copy=False)
    portal_typing_dt = fields.Datetime(copy=False)
