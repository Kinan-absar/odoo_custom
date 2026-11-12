from odoo import models, _

class WorkspaceEPSUser(models.Model):
    _inherit = 'res.users'

    def _pbw_eps_entry_url(self):
        self.ensure_one()
        # Match EPS's employee-linked portal entry condition. No roles are granted.
        return '/my/employee' if self.active and self.share and self.sudo().with_company(self.company_id).employee_id else False

    def _pbw_landing_url(self):
        return self._pbw_eps_entry_url() or super()._pbw_landing_url()

    def _pbw_extra_navigation(self):
        links = list(super()._pbw_extra_navigation())
        if self._pbw_eps_entry_url():
            links.append({'name': _('Employee Portal'), 'url': self._pbw_eps_entry_url(), 'icon': 'fa-users'})
        return links
