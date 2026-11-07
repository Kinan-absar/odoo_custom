import hashlib
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

# Process-local origin markers cannot be forged in an RPC context.
_PBW_HR_GATEWAY_TOKEN = object()
_PBW_HR_BATCH_TOKEN = object()
HR_NOTIFICATION_KINDS = {
    'hr.employee': ('employees', 'employee'),
    'hr.attendance': ('attendance', 'employee'),
    'hr.contract': ('contracts', 'payroll'),
    'hr.work.entry': ('work-entries', 'payroll'),
    'hr.payslip': ('payslips', 'payroll'),
    'hr.payslip.run': ('batches', 'payroll'),
}


def _positive_notification_id(value):
    try:
        ident = int(value)
        if isinstance(value, bool) or ident <= 0 or str(ident) != str(value):
            raise ValueError()
        return ident
    except (ValueError, TypeError):
        raise AccessError(_('Invalid notification identifier.'))


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
    def _assert_owner(self, user):
        if user.id != self.env.uid or not user.active or user._is_public():
            raise AccessError(_('Only your own notifications are available.'))

    @api.model
    def _target_for_user(self, user, record, category):
        """Recheck the actual document boundary before exposing any notice.

        No model/method/URL is supplied by the browser. The narrow Accounting and
        HR gateways remain the source of truth for those sensitive documents.
        """
        user = user.sudo()
        if not user._pbw_has_access() or not record or not record.exists():
            return False
        company = record.company_id
        if not company or company not in user.company_ids:
            return False
        if category not in {area['key'] for area in user._pbw_workspace_areas()}:
            return False
        if category in ('sales', 'purchase', 'accounting') and user.share and not user.with_company(user.company_id).employee_id:
            return False
        if category == 'sales' and record._name == 'sale.order':
            group = 'portal_backend_workspace.sales__group_portal_sales_'
            creator = record.pbw_portal_creator_id
            if not any(user.has_group(group + role) for role in ('creator', 'approver', 'monitor', 'user')):
                return False
            allowed = (user.has_group(group + 'user') or user.has_group(group + 'monitor')
                       or (bool(creator) and user.has_group(group + 'approver'))
                       or (bool(creator) and user in (creator, record.pbw_portal_submitter_id, record.pbw_order_requester_id)))
            if not allowed:
                return False
            path = '/my/workspace/sales/%s' % record.id
        elif category == 'purchase' and record._name == 'purchase.order':
            group = 'portal_backend_workspace.purchase__group_portal_purchase_'
            allowed = (user.has_group(group + 'user')
                       or (record.pbw_portal_preparer_id == user and user.has_group(group + 'preparer'))
                       or (bool(record.pbw_portal_preparer_id) and user.has_group(group + 'approver'))
                       or (record.state in ('purchase', 'done') and user.has_group(group + 'monitor')))
            if not allowed:
                return False
            path = '/my/workspace/purchase/%s' % record.id
        elif category == 'accounting' and record._name == 'account.move':
            kind = {'out_invoice': 'invoices', 'in_invoice': 'bills', 'in_refund': 'refunds', 'entry': 'journals'}.get(record.move_type)
            if not kind:
                return False
            try:
                service = self.env['pbw.portal.accounting.service'].with_user(user)
                service._actor(kind=kind)
                service._record(service._company(company.id), kind, record.id)
            except (AccessError, UserError):
                return False
            path = '/my/workspace/accounting/%s/%s' % (kind, record.id)
        elif category == 'hr' and record._name in HR_NOTIFICATION_KINDS:
            kind, role = HR_NOTIFICATION_KINDS[record._name]
            if not user.has_group('portal_backend_workspace.hr__group_%s_admin' % role):
                return False
            try:
                gateway = self.env['pbw.employee.admin.gateway'].with_user(user)
                gateway._record(gateway._company(company.id), kind, record.id)
            except (AccessError, UserError):
                return False
            path = '/my/workspace/hr/%s/%s' % (kind, record.id)
        else:
            return False
        return '%s?company_id=%s' % (path, company.id)

    @api.model
    def _emit(self, users, record, category, title, body, event_token=None):
        record.ensure_one()
        record = record.sudo()
        for user in users.sudo().filtered(lambda item: item.active and item.id != self.env.uid):
            url = self._target_for_user(user, record, category)
            if not url:
                continue
            identity = event_token or str(record.write_date)
            key = hashlib.sha256(('%s|%s|%s|%s|%s|%s|%s' % (
                record._name, record.id, identity, user.id, category, title, body)).encode()).hexdigest()
            # One row per recipient/event, including concurrent duplicate callbacks.
            self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [int(key[:15], 16)])
            if not self.sudo().search_count([('event_key', '=', key)]):
                self.sudo().create({
                    'user_id': user.id, 'company_id': record.company_id.id,
                    'category': category, 'title': str(title), 'body': str(body or ''),
                    'resource_model': record._name, 'resource_id': record.id,
                    'url': url, 'event_key': key,
                })

    @api.model
    def _visible_domain(self, user):
        user = user.sudo()
        return [('user_id', '=', user.id), ('company_id', 'in', user.company_ids.ids),
                ('category', 'in', [area['key'] for area in user._pbw_workspace_areas()])]

    @api.model
    def _visible_records(self, user, unread_only=False):
        self._assert_owner(user)
        domain = self._visible_domain(user)
        if unread_only:
            domain.append(('read_at', '=', False))
        rows = self.sudo().search(domain, order='id desc')
        cache = {}
        def visible(notice):
            key = (notice.resource_model, notice.resource_id, notice.category)
            if key not in cache:
                # Never index env with an arbitrary untrusted model name.
                expected = {'sales': ('sale.order',), 'purchase': ('purchase.order',),
                            'accounting': ('account.move',), 'hr': tuple(HR_NOTIFICATION_KINDS)}
                cache[key] = False
                if notice.resource_model in expected.get(notice.category, ()) and notice.resource_id > 0:
                    record = self.env[notice.resource_model].sudo().browse(notice.resource_id).exists()
                    cache[key] = self._target_for_user(user, record, notice.category) if record else False
            return bool(cache[key])
        return rows.filtered(visible)

    @api.model
    def _get_notice(self, user, ident):
        self._assert_owner(user)
        ident = _positive_notification_id(ident)
        notice = self.sudo().search(self._visible_domain(user) + [('id', '=', ident)], limit=1)
        if not notice:
            raise AccessError(_('This notification is no longer available.'))
        if notice.resource_model not in ('sale.order', 'purchase.order', 'account.move', *HR_NOTIFICATION_KINDS):
            raise AccessError(_('This notification is no longer available.'))
        record = self.env[notice.resource_model].sudo().browse(notice.resource_id).exists()
        url = self._target_for_user(user, record, notice.category) if record else False
        if not url:
            raise AccessError(_('This document is no longer available with your current permissions.'))
        return notice, url

    @api.model
    def _mark_read(self, user, ident=None, upto_id=None):
        self._assert_owner(user)
        if ident is not None:
            records = self._get_notice(user, ident)[0]
        else:
            records = self._visible_records(user, unread_only=True)
            if upto_id is not None:
                watermark = _positive_notification_id(upto_id)
                records = records.filtered(lambda notice: notice.id <= watermark)
        records.filtered(lambda notice: not notice.read_at).write({'read_at': fields.Datetime.now()})
        return True

    @api.model
    def _unread_snapshot(self, user, limit=20):
        rows = self._visible_records(user, unread_only=True)
        items = []
        for notice in rows[:limit]:
            items.append({
                'key': 'pbw:%s' % notice.id, 'id': notice.id, 'source': 'workspace',
                'category': notice.category, 'title': notice.title, 'body': (notice.body or '')[:250],
                'count': 1, 'url': '/my/workspace/notifications/%s/open' % notice.id,
                'date': fields.Datetime.to_string(notice.create_date),
            })
        return {'items': items, 'count': len(rows), 'watermark': max(rows.ids, default=0)}

    @api.model
    def _notify_hr_event(self, record, operation, event_token=None):
        """Notify only the HR/payroll role that can open the affected record.

        No wage, bank, passport, private-address or payslip-line values are copied
        into notification text. The actor does not receive their own action.
        """
        if record._name not in HR_NOTIFICATION_KINDS:
            return
        kind, role = HR_NOTIFICATION_KINDS[record._name]
        group = self.env.ref('portal_backend_workspace.hr__group_%s_admin' % role, raise_if_not_found=False)
        if not group:
            return  # installation may load native HR data before this addon's groups
        users = self.env['res.users'].sudo().search([
            ('active', '=', True), ('company_ids', 'in', record.company_id.id),
            ('groups_id', 'in', group.id), ('id', '!=', self.env.uid),
        ])
        labels = {
            'save': _('Record updated'), 'start': _('Contract started'), 'close': _('Contract closed'),
            'compute': _('Payslip calculated'), 'validate': _('Record validated'), 'cancel': _('Record cancelled'),
            'compute-batch': _('Payroll batch calculated'), 'validate-batch': _('Payroll batch validated'),
            'generate-payslips': _('Payroll batch payslips generated'), 'line adjustment': _('Payslip input updated'),
            'state': _('HR status changed'), 'archived': _('Employee archived'), 'restored': _('Employee restored'),
        }
        label = labels.get(operation, _('HR record updated'))
        self._emit(users, record, 'hr', '%s: %s' % (label, record.display_name),
                   _('%(action)s by %(user)s.', action=label, user=self.env.user.name), event_token=event_token)

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

    @api.model
    def _can_use_bell(self, user):
        return bool(user.active and not user._is_public() and user._pbw_has_access())

    @api.model
    def _external_bell_items(self, user):
        """Optional bridge hook. The base never imports or queries EPS."""
        return []

    @api.model
    def _get_bell_data(self, user):
        if user.id != self.env.uid or not self._can_use_bell(user):
            raise AccessError(_('Notification access is not available.'))
        has_workspace = bool(user._pbw_has_access())
        snapshot = (self.env['pbw.workspace.notification']._unread_snapshot(user)
                    if has_workspace else {'items': [], 'count': 0, 'watermark': 0})
        external = []
        seen = set()
        for item in self._external_bell_items(user):
            key = item.get('key')
            if key and key not in seen and int(item.get('count', 0)) > 0:
                seen.add(key)
                external.append(item)
        return {
            'version': 1,
            'items': snapshot['items'] + external,
            'unread_count': snapshot['count'] + sum(int(item['count']) for item in external),
            'workspace_unread_count': snapshot['count'],
            'workspace_watermark': snapshot['watermark'],
            'history_url': '/my/workspace/notifications' if has_workspace else False,
            'workspace_summary': self._get_notification_summary(user) if has_workspace else {},
        }
