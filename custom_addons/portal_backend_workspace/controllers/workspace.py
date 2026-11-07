from odoo import http, _
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.portal.controllers.portal import CustomerPortal
from werkzeug.exceptions import Forbidden, NotFound
from odoo.exceptions import AccessError

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
        all_rows=service._visible_records(user)
        rows=all_rows[(page-1)*40:page*40]
        return request.render('portal_backend_workspace.notification_list',{'notification_rows':rows,'page':page,'has_next':len(all_rows)>page*40, 'notification_watermark':max(all_rows.ids, default=0)})

    @http.route('/my/workspace/notifications/read',type='http',auth='user',website=True,methods=['POST'],csrf=True)
    def mark_read(self, ident=None, upto_id=None, **kw):
        user=self._actor()
        try:
            request.env['pbw.workspace.notification']._mark_read(user, ident=ident, upto_id=upto_id)
        except AccessError as exc:
            raise Forbidden(str(exc))
        return request.redirect('/my/workspace/notifications')

    @http.route('/my/workspace/notifications/summary',type='http',auth='user',website=True,methods=['GET'])
    def summary(self, **kw):
        user=self._actor()
        return request.make_json_response(request.env['pbw.notification.seen']._get_notification_summary(user))


    @staticmethod
    def _notification_json(data, status=200):
        return request.make_json_response(data, status=status, headers=[
            ('Cache-Control', 'no-store, private, max-age=0'),
            ('Pragma', 'no-cache'), ('Vary', 'Cookie'),
        ])

    @http.route('/my/workspace/notifications/bell', type='http', auth='user', website=True, methods=['GET'])
    def notification_bell(self, **kw):
        # The optional bridge permits EPS-only users without granting PBW roles.
        try:
            data = request.env['pbw.notification.seen']._get_bell_data(request.env.user)
        except AccessError:
            return self._notification_json({'error': _('Notification access is not available.')}, status=403)
        return self._notification_json(data)

    @http.route('/my/workspace/notifications/read-json', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def notification_read_json(self, ident=None, upto_id=None, **kw):
        user = self._actor()
        try:
            service = request.env['pbw.workspace.notification']
            if ident is not None:
                service._mark_read(user, ident=ident)
            elif upto_id is not None:
                service._mark_read(user, upto_id=upto_id)
            else:
                raise AccessError(_('Select a notification or the displayed workspace updates.'))
            data = request.env['pbw.notification.seen']._get_bell_data(user)
        except AccessError:
            return self._notification_json({'error': _('This notification is no longer available.')}, status=403)
        return self._notification_json(data)

    @http.route('/my/workspace/notifications/<int:ident>/open', type='http', auth='user', website=True, methods=['GET'])
    def notification_open(self, ident, **kw):
        user = self._actor()
        try:
            notice, target = request.env['pbw.workspace.notification']._get_notice(user, ident)
        except AccessError as exc:
            raise Forbidden(str(exc))
        # Read acknowledgements are CSRF-protected POSTs, never mutations by GET.
        return request.redirect(target)
