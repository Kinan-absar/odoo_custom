import hashlib

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class EmployeePortalAttendanceDevice(models.Model):
    _name = 'employee.portal.attendance.device'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Employee Portal Trusted Attendance Device'
    _order = 'state, create_date desc, id desc'

    name = fields.Char(required=True, default='Attendance Device')
    employee_id = fields.Many2one('hr.employee', required=True, index=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    token_hash = fields.Char(required=True, index=True, readonly=True)
    token_prefix = fields.Char(readonly=True)
    state = fields.Selection([
        ('trusted', 'Trusted'),
        ('pending', 'Pending Approval'),
        ('revoked', 'Revoked'),
    ], required=True, default='pending', index=True)
    device_label = fields.Char(string='Device')
    user_agent = fields.Text(readonly=True)
    first_seen_at = fields.Datetime(readonly=True, default=fields.Datetime.now)
    last_seen_at = fields.Datetime(readonly=True)
    trusted_at = fields.Datetime(readonly=True)
    trusted_by = fields.Many2one('res.users', readonly=True)
    revoked_at = fields.Datetime(readonly=True)
    revoked_by = fields.Many2one('res.users', readonly=True)

    _sql_constraints = [
        ('attendance_device_token_hash_uniq', 'unique(token_hash)', 'This attendance device token already exists.'),
    ]

    @api.model
    def _hash_token(self, token):
        return hashlib.sha256((token or '').encode('utf-8')).hexdigest()

    @api.model
    def _device_for_token(self, employee, token):
        if not employee or not token:
            return self.browse()
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('token_hash', '=', self._hash_token(token)),
        ], limit=1)

    @api.model
    def _has_trusted_device(self, employee):
        return bool(self.sudo().search_count([
            ('employee_id', '=', employee.id),
            ('state', '=', 'trusted'),
        ]))

    @api.model
    def register_or_check(self, employee, user, token, device_label=None, user_agent=None):
        token = (token or '').strip()
        if len(token) < 32 or len(token) > 512:
            return {'state': 'invalid', 'message': _('Invalid attendance device token.')}

        Device = self.sudo()
        device = Device._device_for_token(employee, token)
        now = fields.Datetime.now()
        vals = {
            'last_seen_at': now,
            'device_label': (device_label or '')[:128] or device.device_label,
            'user_agent': (user_agent or '')[:1024] or device.user_agent,
        }
        if device:
            device.write(vals)
            return {'state': device.state, 'device_id': device.id}

        has_trusted = Device._has_trusted_device(employee)
        state = 'pending' if has_trusted else 'trusted'
        device = Device.create({
            'name': (device_label or 'Attendance Device')[:128],
            'employee_id': employee.id,
            'user_id': user.id,
            'token_hash': Device._hash_token(token),
            'token_prefix': token[:8],
            'state': state,
            'device_label': (device_label or '')[:128],
            'user_agent': (user_agent or '')[:1024],
            'first_seen_at': now,
            'last_seen_at': now,
            'trusted_at': now if state == 'trusted' else False,
            'trusted_by': user.id if state == 'trusted' else False,
        })
        if state == 'pending':
            device._notify_pending_managers()
        return {'state': state, 'device_id': device.id, 'auto_trusted': state == 'trusted'}

    def _notify_pending_managers(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        group = self.env.ref('employee_portal_suite.group_attendance_manager', raise_if_not_found=False)
        if not activity_type or not group:
            return
        manager_users = self.env['res.users'].sudo().search([
            ('active', '=', True),
            ('groups_id', 'in', group.id),
        ])
        for device in self:
            if manager_users:
                try:
                    device.sudo().message_post(
                        body=_('A new phone is requesting attendance access for %s. Open Trusted Devices to approve or reject it.') % device.employee_id.name,
                        partner_ids=manager_users.mapped('partner_id').ids,
                        message_type='notification',
                        subtype_xmlid='mail.mt_note',
                    )
                except Exception:
                    pass
            for manager in manager_users:
                existing = self.env['mail.activity'].sudo().search([
                    ('res_model', '=', device._name),
                    ('res_id', '=', device.id),
                    ('activity_type_id', '=', activity_type.id),
                    ('user_id', '=', manager.id),
                ], limit=1)
                if existing:
                    continue
                device.sudo().activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=manager.id,
                    summary=_('Approve attendance device'),
                    note=_('A new phone is requesting attendance access for %s. Review the Trusted Devices list and approve or revoke it.') % device.employee_id.name,
                )

    @api.model
    def validate_token(self, employee, token, touch=True):
        device = self.sudo()._device_for_token(employee, token)
        if not device or device.state != 'trusted':
            return False
        if touch:
            device.sudo().write({'last_seen_at': fields.Datetime.now()})
        return device

    def action_trust_replace(self):
        self.ensure_one()
        if self.state == 'trusted':
            return True
        now = fields.Datetime.now()
        others = self.sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'trusted'),
            ('id', '!=', self.id),
        ])
        if others:
            others.write({
                'state': 'revoked',
                'revoked_at': now,
                'revoked_by': self.env.user.id,
            })
        self.env['mail.activity'].sudo().search([
            ('res_model', '=', self._name), ('res_id', '=', self.id),
        ]).unlink()
        self.sudo().write({
            'state': 'trusted',
            'trusted_at': now,
            'trusted_by': self.env.user.id,
            'revoked_at': False,
            'revoked_by': False,
        })
        return True

    def action_revoke(self):
        now = fields.Datetime.now()
        for device in self:
            if device.state == 'revoked':
                continue
            self.env['mail.activity'].sudo().search([
                ('res_model', '=', device._name), ('res_id', '=', device.id),
            ]).unlink()
            device.sudo().write({
                'state': 'revoked',
                'revoked_at': now,
                'revoked_by': self.env.user.id,
            })
        return True
