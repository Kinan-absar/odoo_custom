from odoo import fields, models


class PortalMobileNotification(models.Model):
    _name = 'portal.mobile.notification'
    _description = 'Portal Mobile Notification'
    _order = 'id desc'

    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    title = fields.Char(required=True)
    message = fields.Text(required=True)
    target_url = fields.Char(default='/my/employee')
    delivered = fields.Boolean(default=False, index=True)
    delivered_at = fields.Datetime()
