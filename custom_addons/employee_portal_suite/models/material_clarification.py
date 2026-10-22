"""Material Request clarification: ask, reply, then resume the same approval step."""
import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

CLARIFICATION_FIELDS = frozenset({
    'needs_clarification', 'clarification_stage', 'clarification_question',
    'clarification_reply', 'clarification_requested_by', 'clarification_requested_on',
    'clarification_replied_on', 'clarification_step_name',
})


class MaterialRequestClarification(models.Model):
    _inherit = 'material.request'

    needs_clarification = fields.Boolean(default=False, copy=False, readonly=True, tracking=True)
    clarification_question = fields.Text(readonly=True, copy=False)
    clarification_reply = fields.Text(readonly=True, copy=False)
    clarification_requested_by = fields.Many2one('res.users', readonly=True, copy=False)
    clarification_requested_on = fields.Datetime(readonly=True, copy=False)
    clarification_replied_on = fields.Datetime(readonly=True, copy=False)
    clarification_step_name = fields.Char(readonly=True, copy=False)
    can_reply_clarification = fields.Boolean(compute='_compute_can_reply_clarification')

    @api.depends_context('uid')
    @api.depends('needs_clarification', 'employee_id.user_id', 'clarification_question')
    def _compute_can_reply_clarification(self):
        for rec in self:
            rec.can_reply_clarification = bool(
                rec.needs_clarification and rec.clarification_question
                and rec.employee_id.user_id == self.env.user
            )

    def _check_clarification_write(self, vals):
        if CLARIFICATION_FIELDS.intersection(vals):
            raise UserError(_('Use Request Clarification or Send Reply to update clarification.'))
        for rec in self:
            if not rec.needs_clarification:
                continue
            if 'employee_id' in vals and vals['employee_id'] != rec.employee_id.id:
                raise UserError(_('The requester cannot be changed while clarification is pending.'))
            if vals.get('state') and vals['state'] != rec.state:
                if vals['state'] not in ('returned', 'rejected'):
                    raise UserError(_('Wait for the requester to reply before continuing approval.'))
                # Return/reject ends the outstanding question; history remains in chatter.
                rec._write_clarification({'needs_clarification': False, 'clarification_stage': False})
                rec._close_clarification_activity()

    def _clarification_lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM material_request WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _close_clarification_activity(self):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        self.sudo().activity_ids.filtered(
            lambda activity: activity.activity_type_id == activity_type
            and activity.summary == _('Clarification reply needed')
        ).action_feedback(feedback=_('Clarification completed or closed.'))

    def _clarification_notify(self, user, title, text, path, needs_reply=False):
        self.ensure_one()
        # Chatter preserves every round. Standard Odoo notifications honour the
        # recipient's inbox/email preference; the portal push links to the right page.
        path = self.env['employee.portal.webpush.service']._url_for_user(user, path)
        body = Markup('<p><strong>%s</strong></p><p>%s</p><p><a href="%s">%s</a></p>') % (
            title, text, path, _('Open Material Request'),
        )
        self.sudo().message_post(
            body=body, subject=title, partner_ids=[user.partner_id.id],
            message_type='comment', subtype_xmlid='mail.mt_comment',
            author_id=self.env.user.partner_id.id,
        )
        if needs_reply:
            self.sudo()._schedule_activity(user, _('Clarification reply needed'), body)
        try:
            with self.env.cr.savepoint():
                self.env['employee.portal.webpush.service'].sudo().send_to_user(
                    user, title, text, path=path, kind='approval',
                    tag='mr-clarification-%s' % self.id,
                )
        except Exception:
            # A missing/expired push subscription must not discard a saved reply.
            _logger.exception('Clarification push failed for Material Request %s', self.id)


    def _request_clarification(self, question):
        self.ensure_one()
        if not self._can_toggle_clarification():
            raise UserError(_('Only the current approver can request clarification.'))
        self._clarification_lock()
        if not self._can_toggle_clarification():
            raise UserError(_('The approval step has changed. Reload the request.'))
        if self.needs_clarification and self.clarification_question:
            raise UserError(_('A clarification request is already awaiting a reply.'))
        question = (question or '').strip()
        if not question:
            raise UserError(_('Enter the question you need the requester to answer.'))
        requester = self.employee_id.user_id
        if not requester or not requester.active:
            raise UserError(_('The requesting employee needs an active linked user to receive and answer clarification.'))
        step = self.current_approval_line_id.name if self.state == 'workflow' else dict(self._fields['state'].selection).get(self.state, self.state)
        self._write_clarification({
            'needs_clarification': True, 'clarification_stage': self.state,
            'clarification_question': question, 'clarification_reply': False,
            'clarification_requested_by': self.env.user.id,
            'clarification_requested_on': fields.Datetime.now(),
            'clarification_replied_on': False, 'clarification_step_name': step,
        })
        self._clarification_notify(
            requester, _('Clarification requested: %s') % self.name, question,
            '/my/employee/material/%s' % self.id, needs_reply=True,
        )
        return True

    def _reply_clarification(self, answer):
        self.ensure_one()
        if self.employee_id.user_id != self.env.user:
            raise UserError(_('Only the requesting employee can send this reply.'))
        self._clarification_lock()
        if self.employee_id.user_id != self.env.user:
            raise UserError(_('Only the requesting employee can send this reply.'))
        if not self.needs_clarification or not self.clarification_question:
            raise UserError(_('There is no clarification question awaiting your reply.'))
        answer = (answer or '').strip()
        if not answer:
            raise UserError(_('Enter your clarification reply.'))
        reviewer = self.clarification_requested_by
        self._write_clarification({
            'clarification_reply': answer, 'clarification_replied_on': fields.Datetime.now(),
            'needs_clarification': False, 'clarification_stage': False,
        })
        self._close_clarification_activity()
        # No step transition or automatic approval: the current reviewer continues.
        if self.state == 'workflow':
            reviewers = self.current_approval_line_id.sudo()._effective_users()
        else:
            reviewers = reviewer
        reviewers = reviewers.filtered('active')
        if not reviewers:
            self.sudo().message_post(body=Markup('<p><strong>%s</strong></p><p>%s</p>') % (_('Clarification reply received'), answer), subtype_xmlid='mail.mt_comment')
        for user in reviewers:
            self._clarification_notify(
                user, _('Clarification received: %s') % self.name, answer,
                '/my/employee/material/approvals/%s' % self.id,
            )
        return True

    def _clarification_wizard(self, operation):
        self.ensure_one()
        if operation == 'request' and not self._can_toggle_clarification():
            raise UserError(_('Only the current approver can request clarification.'))
        if operation == 'reply' and not self.can_reply_clarification:
            raise UserError(_('There is no clarification awaiting your reply.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'employee.portal.mr.clarification.wizard',
            'view_mode': 'form', 'target': 'new',
            'name': _('Request Clarification') if operation == 'request' else _('Reply to Clarification'),
            'context': {'default_request_id': self.id, 'default_operation': operation},
        }

    def action_request_clarification(self):
        return self._clarification_wizard('request')

    def action_reply_clarification(self):
        return self._clarification_wizard('reply')


class MaterialClarificationWizard(models.TransientModel):
    _name = 'employee.portal.mr.clarification.wizard'
    _description = 'Material Request Clarification'

    request_id = fields.Many2one('material.request', required=True, readonly=True)
    operation = fields.Selection([('request', 'Request'), ('reply', 'Reply')], required=True, readonly=True)
    question = fields.Text(related='request_id.clarification_question', readonly=True)
    text = fields.Text(string='Message', required=True)

    def action_send(self):
        self.ensure_one()
        if self.operation == 'request':
            self.request_id._request_clarification(self.text)
        else:
            self.request_id._reply_clarification(self.text)
        return {'type': 'ir.actions.act_window_close'}
