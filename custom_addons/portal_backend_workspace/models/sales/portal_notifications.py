"""Sales contributes attention cards through EPS's extension hook; EPS stays unchanged."""
from odoo import api, fields, models, _
from odoo.osv import expression

PREFIX = 'portal_backend_workspace.sales__'


class SalesPortalNotifications(models.Model):
    _inherit = 'pbw.notification.seen'

    report_type = fields.Selection(selection_add=[
        ('sales_approval', 'Sales Approvals'), ('sales_review_update', 'Sales Review Updates')],
        ondelete={'sales_approval':'cascade', 'sales_review_update':'cascade'})

    @api.model
    def _get_sales_notification_summary(self, user):
        user=user.sudo()
        if (not user.active or False
                or (user.share and not user.with_company(user.company_id).employee_id)):
            return {}
        orders=self.env['sale.order'].sudo()
        company=[('company_id','in',user.company_ids.ids)]
        summary={}
        if user.has_group(PREFIX+'group_portal_sales_approver'):
            domain=company+[
                ('pbw_portal_creator_id','!=',False),('pbw_portal_creator_id','!=',user.id),('create_uid','!=',user.id),
                ('pbw_portal_submitter_id','!=',user.id),('pbw_order_requester_id','!=',user.id),
                ('state','in',['draft','sent']),
                '|',('pbw_portal_review_state','=','submitted'),('pbw_order_review_state','=','requested')]
            seen=self._get_last_seen(user.id,'sales_approval')
            count=orders.search_count(domain)
            summary['sales_approval']={'count':count,'new':orders.search_count(domain+[('write_date','>',seen)]) if seen else count,
                'url':'/my/workspace/sales/approvals','label':_('Sales Approvals')}
        if user.has_group(PREFIX+'group_portal_sales_creator'):
            domain=expression.AND([company,[('pbw_sales_decision_at','!=',False)],[
                '|','|',('pbw_portal_creator_id','=',user.id),('pbw_portal_submitter_id','=',user.id),('pbw_order_requester_id','=',user.id)]])
            seen=self._get_last_seen(user.id,'sales_review_update')
            count=orders.search_count(domain)
            summary['sales_review_update']={'count':count,'new':orders.search_count(domain+[('pbw_sales_decision_at','>',seen)]) if seen else count,
                'url':'/my/workspace/sales/updates','label':_('Sales Review Updates')}
        return summary

    @api.model
    def _get_notification_summary(self, user):
        summary=super()._get_notification_summary(user)
        summary.update(self._get_sales_notification_summary(user))
        return summary
