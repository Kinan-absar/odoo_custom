"""Optional read-through adapters; no data-copy job or mandatory custom addon.

Known source contracts: absar_portal_sales 18.0.1.4.14 (customer checkbox and
private confirmation guard), construction_contract_management 18.0.1.8.23
(sale.order.construction_project_id -> project.project).
"""
from importlib import import_module
from odoo import api, models, _
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression


# Customer classification is now owned by the main addon's original field
# contract. No bridge OR-domain or second checkbox is needed.


class SalesProjectDataBridge(models.Model):
    _inherit = 'sale.order'

    @api.model
    def _pbw_sales_project_field(self):
        field = self._fields.get('construction_project_id')
        if field and field.type == 'many2one' and field.comodel_name == 'project.project':
            return 'construction_project_id'
        return super()._pbw_sales_project_field()

    def _pbw_sales_project(self):
        self.ensure_one()
        project = super()._pbw_sales_project()
        # Preserve pre-bridge workspace-only selections without a bulk migration.
        # Existing construction values always win. An explicit save uses the
        # construction field; clearing clears the old local value as well.
        if not project and self._pbw_sales_project_field() != 'pbw_project_id':
            project = self.pbw_project_id
        return project

    @api.model
    def _pbw_sales_project_values(self, project):
        values = super()._pbw_sales_project_values(project)
        if self._pbw_sales_project_field() != 'pbw_project_id':
            values['pbw_project_id'] = False
        return values

    @api.model
    def _pbw_sales_project_search_domain(self, query):
        primary = super()._pbw_sales_project_search_domain(query)
        name = self._pbw_sales_project_field()
        if name != 'pbw_project_id':
            return expression.OR([primary, expression.AND([
                [(name, '=', False)], [('pbw_project_id.name', 'ilike', query)]])])
        return primary

    def _pbw_native_confirmation_context(self):
        self.ensure_one()
        user = self.env.user.sudo(False)
        permissions = self._pbw_review_permissions(user)
        if not (permissions['can_confirm_direct'] or permissions['can_approve_order']):
            raise AccessError(_('This quotation is not authorized for confirmation.'))
        context = dict(super()._pbw_native_confirmation_context())
        legacy_creator = self._fields.get('absar_portal_creator_id')
        # Only the known original Sales workflow has this private method and
        # record schema. Never accept a context token supplied by the browser.
        if (legacy_creator and legacy_creator.type == 'many2one'
                and legacy_creator.comodel_name == 'res.users'
                and hasattr(self, '_absar_portal_can_confirm')):
            try:
                token = import_module('odoo.addons.absar_portal_sales.models.sale_order')._REVIEW_TOKEN
            except (ImportError, AttributeError) as exc:
                raise UserError(_('The installed original Sales approval module is not compatible with this bridge.')) from exc
            context['_absar_sales_confirm_token'] = token
        return context

    def _pbw_after_native_confirmation(self):
        result = super()._pbw_after_native_confirmation()
        for order in self:
            if order.state not in ('sale', 'done'):
                continue
            # Retire the original workflow's pending tasks after authorized
            # confirmation; keep its historical decisions and messages intact.
            if ('absar_portal_creator_id' in order._fields
                    and hasattr(order, '_absar_portal_close_activities')):
                order._absar_portal_close_activities()
        return result
