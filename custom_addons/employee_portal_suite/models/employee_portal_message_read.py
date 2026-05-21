# -*- coding: utf-8 -*-

from odoo import fields, models


class EmployeePortalMessageRead(models.Model):
    _name = 'employee.portal.message.read'
    _description = 'Employee Portal Message Read Marker'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    channel_model = fields.Char(required=True, default='discuss.channel', index=True)
    channel_id = fields.Integer(required=True, index=True)
    last_read_date = fields.Datetime()

    _sql_constraints = [
        (
            'employee_portal_message_read_unique',
            'unique(partner_id, channel_model, channel_id)',
            'A read marker already exists for this partner and channel.',
        ),
    ]
