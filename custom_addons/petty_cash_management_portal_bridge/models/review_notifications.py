from odoo import api, fields, models

class PettyCashNotificationSummary(models.Model):
    _inherit='portal.report.seen'
    report_type=fields.Selection(selection_add=[('petty_review','Petty Cash Reviews'),('petty_result','Petty Cash Updates')],
                                ondelete={'petty_review':'cascade','petty_result':'cascade'})

    @api.model
    def _get_notification_summary(self,user):
        summary=super()._get_notification_summary(user)
        if not user.active or user._is_public():return summary
        Report=self.env['petty.cash'].sudo()
        companies=[('company_id','in',user.company_ids.ids)]
        if Report._is_review_user(user):
            pending=Report.search(companies+[('state','in',['submitted','review_2','manager_approval'])]).filtered(lambda r:r._can_review(user))
            last=self._get_last_seen(user.id,'petty_review')
            summary['petty_review']={'count':len(pending),'new':len(pending.filtered(lambda r:not last or r.write_date>last)),
                'url':'/my/employee/petty-cash/approvals','label':'Petty Cash Reviews'}
        own=Report.search(companies+[('user_id','=',user.id),'|',('state','in',['approved','refused']),('correction_reason','!=',False)])
        if Report._is_review_user(user):
            own |= Report.search(companies+[('state','=','approved'),('journal_entry_id','=',False)])
        if own:
            last=self._get_last_seen(user.id,'petty_result')
            summary['petty_result']={'count':len(own),'new':len(own.filtered(lambda r:not last or r.write_date>last)),
                'url':'/my/employee/petty-cash/approvals?status=approved' if Report._is_review_user(user) else '/my/employee/petty-cash',
                'label':'Petty Cash Updates'}
        return summary
