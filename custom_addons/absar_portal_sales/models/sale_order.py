import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)
_PREFIX = 'absar_portal_sales.'
_REVIEW_TOKEN = object()
_ORDER_FIELDS = {'absar_order_review_state', 'absar_order_requester_id', 'absar_order_approver_id'}
_REVIEW_FIELDS = _ORDER_FIELDS | {'absar_sales_decision_at','absar_portal_creator_id','absar_portal_submitter_id','absar_portal_review_state','absar_portal_approver_id'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    absar_portal_creator_id = fields.Many2one('res.users', string='Prepared By', readonly=True, index=True, copy=False)
    absar_portal_submitter_id = fields.Many2one('res.users',string='Submitted By',readonly=True,copy=False)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved'), ('returned', 'Returned for Correction')],
        string='Sales Review', default='draft', copy=False, tracking=True, index=True)
    absar_portal_review_note = fields.Text(string='Review Notes', copy=False)
    absar_portal_approver_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)

    absar_sales_decision_at = fields.Datetime(string='Latest Sales Decision', readonly=True, copy=False, index=True)
    absar_order_review_state = fields.Selection([
        ('none', 'Not Requested'), ('requested', 'Awaiting Sales Order Approval'),
        ('returned', 'Sales Order Request Returned'), ('approved', 'Sales Order Approved')],
        default='none', string='Sales Order Review', readonly=True, copy=False, tracking=True, index=True)
    absar_order_requester_id = fields.Many2one('res.users', string='Conversion Requested By', readonly=True, copy=False)
    absar_order_approver_id = fields.Many2one('res.users', string='Sales Order Approved By', readonly=True, copy=False)
    absar_requires_review = fields.Boolean(compute='_compute_absar_review_buttons')
    absar_can_submit = fields.Boolean(compute='_compute_absar_review_buttons')
    absar_can_approve = fields.Boolean(compute='_compute_absar_review_buttons')
    absar_can_request_order = fields.Boolean(compute='_compute_absar_review_buttons')
    absar_can_approve_order = fields.Boolean(compute='_compute_absar_review_buttons')

    def _absar_review_permissions(self, user):
        self.ensure_one()
        allowed = bool(user.active and self.company_id in user.company_ids
            and not user.has_group('employee_portal_suite.group_attendance_only')
            and (not user.share or user.sudo().with_company(user.company_id).employee_id))
        creator = allowed and user.has_group(_PREFIX+'group_portal_sales_creator')
        editable = creator and (self.absar_portal_creator_id == user or user.has_group(_PREFIX+'group_portal_sales_user'))
        reviewer = allowed and user.has_group(_PREFIX+'group_portal_sales_approver') and self.absar_portal_creator_id and user not in (self.absar_portal_creator_id, self.absar_portal_submitter_id)
        draft = self.state in ('draft', 'sent')
        return dict(
            requires_review=bool(self.absar_portal_creator_id or creator),
            can_submit=bool(draft and editable and self.absar_portal_review_state in ('draft','returned')),
            can_approve=bool(draft and reviewer and self.absar_portal_review_state == 'submitted'),
            can_request_order=bool(draft and editable and self.absar_portal_review_state == 'approved'
                and self.absar_portal_approver_id and self.absar_order_review_state in ('none','returned')),
            can_approve_order=bool(draft and reviewer and self.absar_portal_review_state == 'approved'
                and self.absar_portal_approver_id and self.absar_order_review_state == 'requested' and self.absar_order_requester_id
                and user != self.absar_order_requester_id))

    @api.depends_context('uid')
    @api.depends('state', 'company_id', 'absar_portal_creator_id', 'absar_portal_submitter_id',
                 'absar_portal_review_state', 'absar_portal_approver_id', 'absar_order_review_state', 'absar_order_requester_id')
    def _compute_absar_review_buttons(self):
        for order in self:
            for key, value in order._absar_review_permissions(self.env.user.sudo(False)).items():
                order['absar_'+key] = value

    def _absar_native_review_access(self):
        if not self.env.user.share:
            self.with_user(self.env.user).sudo(False).check_access('write')

    def _absar_portal_actor(self, role='creator'):
        self.ensure_one()
        user=self.env.user.sudo(False)
        if (not user.active or not user.has_group(_PREFIX+'group_portal_sales_'+role) or
                user.has_group('employee_portal_suite.group_attendance_only') or
                (user.share and not user.sudo().with_company(user.company_id).employee_id) or
                self.company_id not in user.company_ids):
            raise AccessError(_('You do not have permission for this sales review operation.'))
        return user

    def _absar_portal_lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE',[self.id])
        self.invalidate_recordset()

    def _absar_review_write(self, vals):
        return self.sudo().with_context(_absar_sales_review_token=_REVIEW_TOKEN).write(vals)

    def _absar_portal_reviewers(self):
        self.ensure_one()
        return self.env.ref(_PREFIX+'group_portal_sales_approver').sudo().users.filtered(
            lambda u:u.active and u not in (self.absar_portal_creator_id,self.absar_portal_submitter_id,self.absar_order_requester_id) and self.company_id in u.company_ids
            and not u.has_group('employee_portal_suite.group_attendance_only')
            and (not u.share or u.with_company(u.company_id).employee_id))

    @api.model_create_multi
    def create(self, vals_list):
        trusted=self.env.context.get('_absar_sales_review_token') is _REVIEW_TOKEN
        prepared=self.env.user.has_group(_PREFIX+'group_portal_sales_creator')
        copied=[]
        for vals in vals_list:
            vals=dict(vals)
            if not trusted:
                if (vals.get('absar_portal_review_state') not in (None,False,'draft') or vals.get('absar_portal_approver_id')
                        or vals.get('absar_portal_submitter_id') or vals.get('absar_order_review_state') not in (None,False,'none')
                        or vals.get('absar_order_requester_id') or vals.get('absar_order_approver_id') or vals.get('absar_sales_decision_at')):
                    raise AccessError(_('Sales approval can only be recorded through the review actions.'))
                if prepared or vals.get('absar_portal_creator_id'):
                    if vals.get('state') not in (None,False,'draft','sent'):
                        raise AccessError(_('Create a draft quotation and request independent approval.'))
                    vals['absar_portal_creator_id']=self.env.uid
            copied.append(vals)
        return super().create(copied)

    @api.model
    def _absar_portal_sync_salesperson(self):
        orders=self.sudo().search([('absar_portal_creator_id','!=',False),('state','in',('draft','sent'))])
        for order in orders:
            if order.user_id != order.absar_portal_creator_id:
                order.sudo().write({'user_id':order.absar_portal_creator_id.id})
        return True

    def _absar_portal_notify(self, users, title, message):
        self.ensure_one()
        for user in users.filtered('active'):
            path = '/my/employee/sales/%s'%self.id if user.share else '/web#id=%s&model=sale.order&view_type=form'%self.id
            body=Markup('<p><strong>%s</strong></p><p>%s</p><p><a href="%s">Open %s</a></p>') % (title,message,path,self.name)
            # Explicit partner recipients generate inbox/email delivery; the activity also
            # keeps outcomes visible to internal preparers after the notification closes.
            actor=self.env.user
            self.sudo().message_post(body=body,partner_ids=user.partner_id.ids,
                author_id=actor.partner_id.id,
                email_from=actor.email_formatted or self.company_id.partner_id.email_formatted or 'Sales <noreply@localhost>',
                message_type='comment',subtype_xmlid='mail.mt_comment')
        if 'employee.portal.webpush.service' in self.env:
            for user in users:
                try:
                    with self.env.cr.savepoint():
                        self.env['employee.portal.webpush.service'].sudo().send_to_user(user,title,message,
                            path='/my/employee/sales/%s'%self.id if user.share else '/web#id=%s&model=sale.order&view_type=form'%self.id,
                            tag='sales-%s'%self.id)
                except Exception:
                    _logger.warning('Optional sales webpush failed for order %s',self.id,exc_info=True)

    def _absar_portal_close_activities(self):
        self.sudo().activity_ids.filtered(lambda a:a.summary in ('Sales quotation review: %s'%self.name,'Sales order conversion review: %s'%self.name)).action_feedback(feedback=_('Sales review completed.'))

    def _absar_portal_notify_reviewers(self, conversion=False):
        self.ensure_one()
        users=self._absar_portal_reviewers()
        if not users:
            raise UserError(_('No independent Sales Approver is available for this company. Ask your administrator to assign one.'))
        self._absar_portal_notify(users,(_('Sales order conversion %s awaiting approval') if conversion else _('Quotation %s awaiting approval'))%self.name,
            (_('%s requested approval to convert this quotation into a Sales Order.') if conversion else _('%s submitted this quotation for your review.'))%
            (self.absar_order_requester_id if conversion else self.absar_portal_submitter_id or self.absar_portal_creator_id).name)
        for user in users.filtered(lambda u:not u.share and u.has_group('sales_team.group_sale_salesman')):
            self.sudo().activity_schedule('mail.mail_activity_data_todo',user_id=user.id,
                summary=('Sales order conversion review: %s' if conversion else 'Sales quotation review: %s')%self.name,
                note=_('Review the request, then approve or return it.'))

    def _absar_portal_notify_creator(self,message):
        self.ensure_one()
        self._absar_review_write({'absar_sales_decision_at':fields.Datetime.now()})
        users = self.absar_portal_creator_id | self.absar_portal_submitter_id | self.absar_order_requester_id
        self._absar_portal_notify(users,_('Quotation %s review update')%self.name,message)
        for user in users.filtered(lambda u:u.active and not u.share and u.has_group('sales_team.group_sale_salesman')):
            summary = 'Sales review update: %s'%self.name
            self.sudo().activity_ids.filtered(lambda a:a.summary == summary and a.user_id == user).action_feedback()
            path = '/web#id=%s&model=sale.order&view_type=form'%self.id
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=user.id, summary=summary,
                note=Markup('<p>%s</p><p><a href="%s">Open %s</a></p>') % (message,path,self.name))

    def _absar_portal_submit(self):
        user=self._absar_portal_actor()
        self._absar_portal_lock()
        self._absar_native_review_access()
        operator=user.has_group(_PREFIX+'group_portal_sales_user')
        if (self.state not in ('draft','sent') or self.absar_portal_review_state not in ('draft','returned') or
                (self.absar_portal_creator_id != user and not operator)):
            raise UserError(_('Only an accessible editable quotation can be submitted.'))
        lines=self.order_line.filtered(lambda l:not l.display_type)
        if not lines or any(l.product_uom_qty<=0 for l in lines):
            raise ValidationError(_('Add at least one line with a positive quantity.'))
        if self.absar_proposal_type=='technical' and self.absar_proposal_payment_ids:
            if float_compare(sum(self.absar_proposal_payment_ids.mapped('percentage')),100,precision_digits=2):
                raise ValidationError(_('Payment milestones must total 100 percent.'))
        self._absar_review_write({'absar_portal_creator_id':self.absar_portal_creator_id.id or user.id,'absar_portal_submitter_id':user.id,'absar_portal_review_state':'submitted','absar_portal_approver_id':False,'absar_portal_review_note':False, 'absar_order_review_state':'none',
            'absar_order_requester_id':False,'absar_order_approver_id':False})
        self._absar_portal_notify_reviewers()
        return True

    def action_absar_portal_submit(self):
        if self.env.user.share:
            raise AccessError(_('Submit through the sales portal.'))
        self.check_access('write')
        for order in self:order._absar_portal_submit()
        return {'type':'ir.actions.client','tag':'reload'}

    def action_absar_portal_approve(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            order._absar_native_review_access()
            if (not order.absar_portal_creator_id or order.absar_portal_review_state!='submitted' or
                    order.state not in ('draft','sent') or user in (order.absar_portal_creator_id,order.absar_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted quotation can be approved.'))
            order._absar_review_write({'absar_portal_review_state':'approved','absar_portal_approver_id':user.id})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Approved by %s. The quotation can now be printed. Request Sales Order approval when ready to convert it.')%user.name)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_absar_portal_return(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            order._absar_native_review_access()
            if (not order.absar_portal_creator_id or order.absar_portal_review_state not in ('submitted','approved') or
                    order.state not in ('draft','sent') or user in (order.absar_portal_creator_id,order.absar_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted or approved quotation can be returned.'))
            note=(order.absar_portal_review_note or '').strip()
            if not note:raise ValidationError(_('Explain the correction required.'))
            order._absar_review_write({'absar_portal_review_state':'returned','absar_portal_approver_id':False, 'absar_order_review_state':'none',
                'absar_order_approver_id':False})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Returned for correction: %s')%note)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_absar_request_order(self):
        for order in self:
            user=order._absar_portal_actor();order._absar_portal_lock()
            order._absar_native_review_access()
            if not order._absar_review_permissions(user)['can_request_order']:
                raise UserError(_('Only an approved quotation can be submitted for Sales Order approval.'))
            order._absar_review_write({'absar_order_review_state':'requested','absar_order_requester_id':user.id,
                'absar_order_approver_id':False,'absar_portal_review_note':False})
            order._absar_portal_notify_reviewers(conversion=True)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_absar_approve_order(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            order._absar_native_review_access()
            if not order._absar_review_permissions(user)['can_approve_order']:
                raise UserError(_('Only an independent approver can approve a pending Sales Order request.'))
            # Confirmation and approval share this transaction; native validation failure
            # rolls back the decision, activities and notifications together.
            order.with_company(order.company_id).with_context(_absar_sales_confirm_token=_REVIEW_TOKEN, validate_analytic=True).action_confirm()
            if order.state not in ('sale','done'):
                raise UserError(_('Sales Order confirmation did not complete. Resolve the native validation first.'))
            order._absar_review_write({'absar_order_review_state':'approved','absar_order_approver_id':user.id})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Sales Order conversion approved by %s. %s is now a Sales Order.')%(user.name,order.name))
        return {'type':'ir.actions.client','tag':'reload'}

    def action_absar_return_order(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            order._absar_native_review_access()
            if not order._absar_review_permissions(user)['can_approve_order']:
                raise UserError(_('Only an independent approver can return a pending Sales Order request.'))
            note=(order.absar_portal_review_note or '').strip()
            if not note:raise ValidationError(_('Explain the correction required in Review Notes.'))
            order._absar_review_write({'absar_order_review_state':'returned','absar_order_approver_id':False})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Sales Order request returned: %s')%note)
        return {'type':'ir.actions.client','tag':'reload'}

    def _absar_portal_can_confirm(self,user):
        # Compatibility for older templates: preparers never get a native Confirm.
        return False

    def action_confirm(self):
        actor=self.env.user.sudo(False)
        if self.env.context.get('_absar_sales_confirm_token') is not _REVIEW_TOKEN:
            if self.filtered('absar_portal_creator_id') or actor.has_group(_PREFIX+'group_portal_sales_creator'):
                raise UserError(_('Request Sales Order approval. The approver will approve the conversion.'))
        return super().action_confirm()

    def _absar_portal_invalidate_review(self):
        if self.env.context.get('_absar_sales_confirm_token') is _REVIEW_TOKEN:
            return
        for order in self.sorted('id'):
            if order.absar_portal_creator_id and order.state in ('draft','sent') and order.absar_portal_review_state in ('submitted','approved'):
                order._absar_portal_lock()
                order._absar_review_write({'absar_portal_review_state':'returned','absar_portal_approver_id':False,
                    'absar_order_review_state':'none', 'absar_order_requester_id':False,'absar_order_approver_id':False,
                    'absar_portal_review_note':_('Quotation contents changed. Check and resubmit for approval.')})
                order._absar_portal_close_activities()

    def write(self,vals):
        if vals.get('state')=='sale' and self.env.context.get('_absar_sales_confirm_token') is not _REVIEW_TOKEN:
            if self.filtered('absar_portal_creator_id') or self.env.user.has_group(_PREFIX+'group_portal_sales_creator'):
                raise AccessError(_('Request Sales Order approval; the approver confirms the conversion.'))
        if _REVIEW_FIELDS.intersection(vals) and self.env.context.get('_absar_sales_review_token') is not _REVIEW_TOKEN:
            raise AccessError(_('Sales approval metadata can only be changed through the review actions.'))
        content={'date_order','partner_id','company_id','currency_id','pricelist_id','payment_term_id','validity_date','order_line','note',
                 'construction_project_id','absar_proposal_type','absar_proposal_title','absar_proposal_section_ids','absar_proposal_payment_ids'}
        if content.intersection(vals):self._absar_portal_invalidate_review()
        return super().write(vals)

    def action_draft(self):
        result=super().action_draft()
        self.filtered('absar_portal_creator_id')._absar_review_write({'absar_portal_review_state':'draft','absar_portal_approver_id':False,'absar_portal_review_note':False, 'absar_order_review_state':'none',
            'absar_order_requester_id':False,'absar_order_approver_id':False})
        return result


class SaleOrderLine(models.Model):
    _inherit='sale.order.line'

    @api.model_create_multi
    def create(self,vals_list):
        self.env['sale.order'].browse(list({v['order_id'] for v in vals_list if v.get('order_id')}))._absar_portal_invalidate_review()
        return super().create(vals_list)

    def write(self,vals):
        if {'product_id','name','product_uom_qty','price_unit','discount','tax_id','product_uom','display_type','analytic_distribution'}.intersection(vals):
            self.order_id._absar_portal_invalidate_review()
        return super().write(vals)

    def unlink(self):
        self.order_id._absar_portal_invalidate_review()
        return super().unlink()
