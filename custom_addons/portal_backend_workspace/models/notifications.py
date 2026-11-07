import hashlib
from odoo import api, fields, models, _
from odoo.exceptions import AccessError

class WorkspaceNotification(models.Model):
    _name = 'pbw.workspace.notification'
    _description = 'Workspace Notification'
    _order = 'id desc'
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', required=True, index=True, ondelete='cascade')
    category = fields.Selection([('sales','Sales'),('purchase','Purchase'),('accounting','Accounting'),('hr','HR')], required=True)
    title = fields.Char(required=True)
    body = fields.Text()
    resource_model = fields.Char(required=True)
    resource_id = fields.Integer(required=True)
    url = fields.Char(required=True)
    read_at = fields.Datetime(index=True)
    event_key = fields.Char(required=True, index=True)
    _sql_constraints = [('event_unique', 'unique(event_key)', 'This event was already notified.')]

    @api.model
    def _emit(self, users, record, category, title, body):
        record.ensure_one()
        company = record.company_id
        if not company or record._name not in ('sale.order','purchase.order','account.move'):
            return
        if record._name == 'account.move':
            kind = {'out_invoice':'invoices','in_invoice':'bills','in_refund':'refunds','entry':'journals'}.get(record.move_type)
            if not kind:
                return
            url = '/my/workspace/accounting/%s/%s?company_id=%s' % (kind, record.id, company.id)
        else:
            url = '/my/workspace/%s/%s?company_id=%s' % (category, record.id, company.id)
        for user in users.sudo().filtered('active'):
            if company not in user.company_ids or not user._pbw_has_access():
                continue
            if category not in [a['key'] for a in user._pbw_workspace_areas()]:
                continue
            key = hashlib.sha256(('%s|%s|%s|%s|%s|%s|%s' % (record._name, record.id, record.write_date, user.id, category, title, body)).encode()).hexdigest()
            # Serialize identical events rather than risk a duplicate insert rolling back a review.
            self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [int(key[:15],16)])
            if not self.sudo().search_count([('event_key','=',key)]):
                self.sudo().create({'user_id':user.id,'company_id':company.id,'category':category,'title':title,'body':str(body or ''),'resource_model':record._name,'resource_id':record.id,'url':url,'event_key':key})

    @api.model
    def _visible_domain(self, user):
        user = user.sudo()
        return [('user_id','=',user.id),('company_id','in',user.company_ids.ids),('category','in',[a['key'] for a in user._pbw_workspace_areas()])]

    @api.model
    def _mark_read(self, user, ident=None):
        if user.id != self.env.uid and not self.env.su:
            raise AccessError(_('Only your own notifications can be marked read.'))
        domain = self._visible_domain(user) + [('read_at','=',False)]
        if ident:
            domain.append(('id','=',int(ident)))
        self.sudo().search(domain).write({'read_at':fields.Datetime.now()})

class NotificationSeen(models.Model):
    _name = 'pbw.notification.seen'
    _description = 'Workspace Notification Read Marker'
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    report_type = fields.Selection([('inbox','Workspace Updates'),('accounting_approval','Accounting Approvals')], required=True)
    last_seen = fields.Datetime(required=True, default=fields.Datetime.now)
    _sql_constraints = [('user_type_unique','unique(user_id,report_type)','One marker per user and category.')]

    @api.model
    def _get_last_seen(self, user_id, report_type):
        return self.sudo().search([('user_id','=',user_id),('report_type','=',report_type)],limit=1).last_seen

    @api.model
    def _get_last_seen_map(self, user_id):
        return {r.report_type:r.last_seen for r in self.sudo().search([('user_id','=',user_id)])}

    @api.model
    def _mark_seen(self, user_id, report_type):
        if user_id != self.env.uid and not self.env.su:
            raise AccessError(_('Only your own notifications can be marked read.'))
        # Fixed enum values; no model names or arbitrary fields supplied by the browser.
        allowed = dict(self._fields['report_type']._description_selection(self.env))
        if report_type not in allowed:
            raise AccessError(_('Unsupported notification category.'))
        lock = int(hashlib.sha256(('%s:%s' % (user_id,report_type)).encode()).hexdigest()[:15],16)
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)',[lock])
        rec=self.sudo().search([('user_id','=',user_id),('report_type','=',report_type)],limit=1)
        if rec:rec.write({'last_seen':fields.Datetime.now()})
        else:self.sudo().create({'user_id':user_id,'report_type':report_type})
        return True

    @api.model
    def _get_notification_summary(self, user):
        user=user.sudo()
        if not user._pbw_has_access():return {}
        inbox=self.env['pbw.workspace.notification'].sudo()
        domain=inbox._visible_domain(user)
        summary={'inbox':{'count':inbox.search_count(domain),'new':inbox.search_count(domain+[('read_at','=',False)]),'label':_('Workspace Updates'),'url':'/my/workspace/notifications'}}
        if user.has_group('portal_backend_workspace.accounting__group_approver'):
            journals=[]
            for company in user.company_ids:
                journals+=company.pbw_accounting_journal_ids.ids
                if user.has_group('portal_backend_workspace.accounting__group_customer_invoicing'):
                    journals+=self.env['account.journal'].sudo().search([('company_id','=',company.id),('type','=','sale')]).ids
            domain=[('company_id','in',user.company_ids.ids),('journal_id','in',journals),('state','=','draft'),('pbw_accounting_review','=','submitted'),('pbw_accounting_issuer_id','!=',user.id)]
            moves=self.env['account.move'].sudo()
            seen=self._get_last_seen(user.id,'accounting_approval')
            count=moves.search_count(domain)
            summary['accounting_approval']={'count':count,'new':moves.search_count(domain+[('write_date','>',seen)]) if seen else count,'label':_('Accounting Approvals'),'url':'/my/workspace/accounting'}
        return summary
