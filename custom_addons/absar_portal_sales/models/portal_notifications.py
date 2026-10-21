"""Sales contributes attention cards through EPS's extension hook; EPS stays unchanged."""
from odoo import api, fields, models, _
from odoo.osv import expression

PREFIX = 'absar_portal_sales.'


class SalesPortalNotifications(models.Model):
    _inherit = 'portal.report.seen'

    report_type = fields.Selection(selection_add=[
        ('sales_approval', 'Sales Approvals'), ('sales_review_update', 'Sales Review Updates')],
        ondelete={'sales_approval':'cascade', 'sales_review_update':'cascade'})

    @api.model
    def _get_sales_notification_summary(self, user):
        user=user.sudo()
        if (not user.active or user.has_group('employee_portal_suite.group_attendance_only')
                or (user.share and not user.with_company(user.company_id).employee_id)):
            return {}
        orders=self.env['sale.order'].sudo()
        company=[('company_id','in',user.company_ids.ids)]
        summary={}
        if user.has_group(PREFIX+'group_portal_sales_approver'):
            domain=company+[
                ('absar_portal_creator_id','!=',False),('absar_portal_creator_id','!=',user.id),
                ('absar_portal_submitter_id','!=',user.id),('absar_order_requester_id','!=',user.id),
                ('state','in',['draft','sent']),
                '|',('absar_portal_review_state','=','submitted'),('absar_order_review_state','=','requested')]
            seen=self._get_last_seen(user.id,'sales_approval')
            count=orders.search_count(domain)
            summary['sales_approval']={'count':count,'new':orders.search_count(domain+[('write_date','>',seen)]) if seen else count,
                'url':'/my/employee/sales/approvals','label':_('Sales Approvals')}
        if user.has_group(PREFIX+'group_portal_sales_creator'):
            domain=expression.AND([company,[('absar_sales_decision_at','!=',False)],[
                '|','|',('absar_portal_creator_id','=',user.id),('absar_portal_submitter_id','=',user.id),('absar_order_requester_id','=',user.id)]])
            seen=self._get_last_seen(user.id,'sales_review_update')
            count=orders.search_count(domain)
            summary['sales_review_update']={'count':count,'new':orders.search_count(domain+[('absar_sales_decision_at','>',seen)]) if seen else count,
                'url':'/my/employee/sales/updates','label':_('Sales Review Updates')}
        return summary

    @api.model
    def _get_notification_summary(self, user):
        summary=super()._get_notification_summary(user)
        summary.update(self._get_sales_notification_summary(user))
        return summary
