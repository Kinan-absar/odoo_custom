from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.portal.controllers.portal import CustomerPortal
from werkzeug.exceptions import Forbidden, NotFound

class WorkspaceLogin(Home):
    def _login_redirect(self, uid, redirect=None):
        destination=super()._login_redirect(uid,redirect=redirect)
        user=request.env['res.users'].sudo().browse(uid)
        if user.share and user._pbw_has_access():
            if redirect and redirect.split('?')[0] not in ('/my','/my/home','/'):
                return destination
            # Do not overrule another product's explicit landing decision.
            if destination and destination.split('?')[0] not in ('/my','/my/home','/','/odoo','/web'):
                return destination
            return user._pbw_landing_url() or destination
        return destination

class WorkspacePortalHome(CustomerPortal):
    @http.route()
    def home(self, **kw):
        user=request.env.user
        if user.share and user._pbw_has_access():
            return request.redirect(user._pbw_landing_url() or '/my/workspace')
        return super().home(**kw)

class Workspace(http.Controller):
    def _actor(self):
        if not request.env.user._pbw_has_access():
            raise Forbidden(_('No workspace access has been assigned to this account.'))
        return request.env.user

    @http.route('/my/workspace',type='http',auth='user',website=True,methods=['GET'])
    def index(self, **kw):
        user=self._actor()
        summary = request.env['pbw.notification.seen']._get_notification_summary(user)
        return request.render('portal_backend_workspace.workspace_home', {
            'workspace_areas': user._pbw_workspace_areas(),
            'workspace_attention': user._pbw_attention_items(summary),
            'ep_notif_summary': summary,
            'ep_notif_unread_total': sum(v.get('new', 0) for v in summary.values()),
        })

    @http.route('/my/workspace/notifications',type='http',auth='user',website=True,methods=['GET'])
    def notifications(self, page=1, **kw):
        user=self._actor();service=request.env['pbw.workspace.notification'].sudo()
        try:page=max(1,min(int(page),10000))
        except (ValueError,TypeError):raise NotFound()
        domain=service._visible_domain(user)
        rows=service.search(domain,offset=(page-1)*40,limit=40)
        return request.render('portal_backend_workspace.notification_list',{'notification_rows':rows,'page':page,'has_next':service.search_count(domain)>page*40})

    @http.route('/my/workspace/notifications/read',type='http',auth='user',website=True,methods=['POST'],csrf=True)
    def mark_read(self, ident=None, **kw):
        user=self._actor()
        try:ident=int(ident) if ident else None
        except (ValueError,TypeError):raise NotFound()
        request.env['pbw.workspace.notification']._mark_read(user,ident)
        return request.redirect('/my/workspace/notifications')

    @http.route('/my/workspace/notifications/summary',type='http',auth='user',website=True,methods=['GET'])
    def summary(self, **kw):
        user=self._actor()
        return request.make_json_response(request.env['pbw.notification.seen']._get_notification_summary(user))
