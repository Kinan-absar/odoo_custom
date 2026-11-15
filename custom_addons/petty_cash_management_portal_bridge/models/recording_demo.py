from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PettyCashPortalRecordingDemo(models.Model):
    _inherit = 'petty.cash.recording.demo'

    include_portal = fields.Boolean(default=True, string='Include portal employee examples')
    portal_user_id = fields.Many2one('res.users', string='Existing Portal Recording User',
        default=lambda self:self._default_portal_recording_user(),
        domain="[('active','=',True),('share','=',True),('company_ids','in',company_id)]",
        help='Choose the existing Employee Portal login you will use for recording. No user or employee is created.')
    portal_recording_url = fields.Char(default='/my/employee/petty-cash', readonly=True)

    @api.model
    def _default_portal_recording_user(self):
        portal = self.env.ref('base.group_portal')
        users = self.env['res.users'].sudo().search([
            ('active','=',True),('share','=',True),('groups_id','in',portal.ids),
            ('company_ids','in',self.env.company.ids)], order='id')
        # Prefer an account already linked to an employee when HR is installed.
        if 'employee_ids' in users._fields:
            linked = users.filtered(lambda u:u.employee_ids.filtered(lambda e:e.company_id==self.env.company))
            if linked:return linked[0]
        return users[:1]

    def _demo_validate(self):
        result = super()._demo_validate()
        if self.include_portal:
            user = self.portal_user_id
            if (not user or not user.active or user._is_public() or not user.share
                    or self.env.ref('base.group_portal') not in user.groups_id
                    or self.env.ref('base.group_user') in user.groups_id
                    or self.company_id not in user.company_ids):
                raise UserError(_('Choose an active existing Portal user with access to this company. Internal users cannot be used as the portal recording account.'))
            if not self.prepare_roles and not user.has_group('petty_cash_management.group_portal_petty_cash_user'):
                raise UserError(_('Enable petty cash roles for the selected recording accounts, or choose a portal user who already has Portal Petty Cash User access.'))
        return result

    def _demo_prepare_roles(self):
        super()._demo_prepare_roles()
        if self.include_portal and self.prepare_roles:
            group = self.env.ref('petty_cash_management.group_portal_petty_cash_user')
            if group not in self.portal_user_id.groups_id:
                # Only a same-type portal extension; no Internal User membership.
                self.portal_user_id.write({'groups_id':[(4,group.id)]})

    def _demo_owners(self):
        owners = super()._demo_owners()
        if self.include_portal:owners.append(('Portal',self.portal_user_id))
        return owners

