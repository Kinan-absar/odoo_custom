"""A native action host, not a generic elevated ORM proxy."""
import json
from markupsafe import Markup
from odoo import http, _
from odoo.http import request
from werkzeug.exceptions import Gone, NotFound
from .portal_prepare import PortalPurchasePrepare, BASE, PREFIX
from ..models.native_access import guard_actor


def script_json(value):
    return Markup(json.dumps(value, default=str).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


class NativePurchaseWorkspace(PortalPurchasePrepare):
    def _native_render(self, section='rfq', po_id=None, new=False):
        user = self._actor()
        guard_actor(request.env)
        # These are the installed native actions/views, including extension views.
        rfq = request.env.ref('purchase.purchase_rfq').sudo()._get_action_dict()
        orders = request.env.ref('purchase.purchase_form_action').sudo()._get_action_dict()
        products = request.env.ref('purchase.product_normal_action_puchased').sudo()._get_action_dict()
        actions = {'rfq': rfq, 'orders': orders, 'products': products}
        for action in actions.values():
            action['target'] = 'current'
        actions['mr'] = {
            'type': 'ir.actions.act_window', 'name': _('Approved Material Requests'),
            'res_model': 'material.request', 'view_mode': 'list,form',
            'views': [(request.env.ref('employee_portal_suite.view_material_request_list').id, 'list'),
                      (request.env.ref('employee_portal_suite.view_material_request_form').id, 'form')],
            'domain': [('state', '=', 'approved'), ('no_po_required', '=', False)],
            'context': {'create': False}, 'target': 'current',
        }
        if section in ('approvals', 'confirmations'):
            role = 'approver' if section == 'approvals' else 'confirmer'
            self._actor(role)
            action = dict(rfq)
            action['name'] = _('Purchase Approvals') if role == 'approver' else _('Purchase Confirmations')
            action['domain'] = [('absar_portal_review_state', '=', 'submitted' if role == 'approver' else 'approved')]
        else:
            if section not in actions:
                raise NotFound()
            action = dict(actions[section])
        if po_id or new:
            self._actor('preparer' if new else None)
            if po_id:
                request.env['purchase.order'].browse(po_id).check_access('read')
            action.update(res_model='purchase.order', views=[(False, 'form')], view_mode='form',
                          res_id=po_id or False, context={})
        info = request.env['ir.http'].session_info()
        # Native company service needs this metadata. Keep the genuine is_internal,
        # is_admin and is_system flags; never impersonate a backend session.
        companies = user.sudo().company_ids
        info['user_companies'] = {
            'current_company': request.env.company.id,
            'allowed_companies': {c.id: {'id': c.id, 'name': c.name, 'sequence': c.sequence,
                'parent_id': c.parent_id.id if c.parent_id in companies else False,
                'child_ids': [i for i in c.child_ids.ids if i in companies.ids]} for c in companies},
            'disallowed_ancestor_companies': {},
        }
        boot = {'action': action, 'actions': actions,
                'roles': {r: user.has_group(PREFIX + 'group_portal_purchase_' + r)
                          for r in ('preparer', 'approver', 'monitor', 'confirmer', 'product_creator')}}
        response = request.render('absar_portal_purchase_monitor.native_purchase_shell', {
            'session_json': script_json(info), 'workspace_json': script_json(boot),
            'title': _('Purchase'), 'debug': request.session.debug,
        })
        response.headers['Cache-Control'] = 'no-store'
        return response

    @http.route([BASE, BASE + '/approvals', BASE + '/confirmations'], type='http', auth='user', website=False)
    def listing(self, **kw):
        section = request.httprequest.path.rstrip('/').rsplit('/', 1)[-1]
        return self._native_render(section if section in ('approvals', 'confirmations') else 'rfq')

    @http.route([BASE + '/new', BASE + '/<int:po_id>'], type='http', auth='user', website=False, methods=['GET'])
    def editor(self, po_id=None, **kw):
        return self._native_render(po_id=po_id, new=not po_id)

    @http.route([BASE + '/app', BASE + '/app/<path:action_path>'], type='http', auth='user', website=False)
    def workspace(self, action_path=None, section='rfq', **kw):
        return self._native_render(section=section)

    # Override each inherited endpoint, rather than registering competing routes.
    @http.route()
    def save(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def preview(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def lookup(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def vendor_defaults(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def product_defaults(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def create_product(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

    @http.route()
    def decision(self, **kw):
        raise Gone(_('Open the native Purchase workspace and retry the operation there.'))

