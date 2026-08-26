import uuid as uuid_lib

from odoo import api, fields, models


class PortalCallContact(models.Model):
    """Explicit allow-list of who is allowed to call whom.

    A portal user can only call, and only be called by, an internal user
    that has an active entry here. This keeps the feature opt-in and
    prevents portal users from being able to enumerate / ring arbitrary
    internal users.
    """
    _name = 'portal.call.contact'
    _description = 'Portal Call Contact'
    _rec_name = 'display_name'

    portal_user_id = fields.Many2one(
        'res.users', string='Portal User', required=True, ondelete='cascade',
        domain=lambda self: [
            ('groups_id', 'in', [self.env.ref('base.group_portal').id]),
            ('active', '=', True),
        ],
    )
    internal_user_id = fields.Many2one(
        'res.users', string='Internal User', required=True, ondelete='cascade',
        domain=[('share', '=', False)],
    )
    active = fields.Boolean(default=True)
    note = fields.Char(help='Optional label, e.g. "HR Manager" or the request this contact relates to.')

    display_name = fields.Char(compute='_compute_display_name', store=False)

    _sql_constraints = [
        ('portal_internal_uniq', 'unique(portal_user_id, internal_user_id)',
         'This portal/internal user pair is already a call contact.'),
    ]

    @api.depends('portal_user_id', 'internal_user_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s ↔ %s" % (
                rec.portal_user_id.name or '?', rec.internal_user_id.name or '?')


class PortalCallSession(models.Model):
    _name = 'portal.call.session'
    _description = 'Portal Call Session'
    _order = 'create_date desc'
    _rec_name = 'uuid'

    uuid = fields.Char(required=True, index=True, copy=False, default=lambda self: str(uuid_lib.uuid4()))
    caller_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    callee_id = fields.Many2one('res.users', required=True, ondelete='cascade')
    call_type = fields.Selection([('audio', 'Audio'), ('video', 'Video')], default='audio', required=True)
    state = fields.Selection([
        ('ringing', 'Ringing'),
        ('ongoing', 'Ongoing'),
        ('rejected', 'Rejected'),
        ('missed', 'Missed'),
        ('ended', 'Ended'),
    ], default='ringing', required=True)
    start_date = fields.Datetime(default=fields.Datetime.now)
    answered_date = fields.Datetime()
    end_date = fields.Datetime()

    def _other_party(self, user):
        self.ensure_one()
        return self.callee_id if user.id == self.caller_id.id else self.caller_id

    def _is_participant(self, user):
        self.ensure_one()
        return user.id in (self.caller_id.id, self.callee_id.id)

    @api.autovacuum
    def _gc_stale_ringing_sessions(self):
        """Close abandoned ringing sessions that were never answered."""
        stale_before = fields.Datetime.subtract(fields.Datetime.now(), minutes=5)
        stale = self.sudo().search([
            ('state', '=', 'ringing'),
            ('start_date', '<', stale_before),
        ])
        if stale:
            stale.write({
                'state': 'missed',
                'end_date': fields.Datetime.now(),
            })


class PortalCallSignal(models.Model):
    """Lightweight signalling mailbox, polled by the client-side JS.

    Deliberately implemented as a plain polled queue (not the mail bus)
    so the calling feature has no dependency on Discuss/bus internals
    and behaves identically on the portal and backend.
    """
    _name = 'portal.call.signal'
    _description = 'Portal Call Signal'
    _order = 'id asc'
    _log_access = False

    session_id = fields.Many2one('portal.call.session', required=True, ondelete='cascade', index=True)
    recipient_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    event = fields.Selection([
        ('incoming', 'Incoming Call'),
        ('signal', 'WebRTC Signal'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('ended', 'Ended'),
        ('cancelled', 'Cancelled (no answer)'),
    ], required=True)
    payload = fields.Text(help='JSON-encoded payload (SDP offer/answer, ICE candidate, caller info, ...).')
    consumed = fields.Boolean(default=False, index=True)

    @api.autovacuum
    def _gc_old_signals(self):
        """Remove consumed / stale signals so this table never grows unbounded."""
        domain = [
            '|',
            ('consumed', '=', True),
            ('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), hours=6)),
        ]
        self.sudo().search(domain).unlink()
