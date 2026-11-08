import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare
from odoo.osv import expression

_logger = logging.getLogger(__name__)
_PREFIX = 'portal_backend_workspace.sales__'
_REVIEW_TOKEN = object()
_ORDER_FIELDS = {'pbw_order_review_state', 'pbw_order_requester_id', 'pbw_order_approver_id'}
_REVIEW_FIELDS = _ORDER_FIELDS | {'pbw_sales_decision_at','pbw_portal_creator_id','pbw_portal_submitter_id','pbw_portal_review_state','pbw_portal_approver_id', 'pbw_direct_confirmed_by_id'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    pbw_portal_creator_id = fields.Many2one('res.users', string='Prepared By', readonly=True, index=True, copy=False)
    pbw_portal_submitter_id = fields.Many2one('res.users',string='Submitted By',readonly=True,copy=False)
    pbw_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved'), ('returned', 'Returned for Correction')],
        string='Sales Review', default='draft', copy=False, tracking=True, index=True)
    pbw_portal_review_note = fields.Text(string='Review Notes', copy=False)
    pbw_portal_approver_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)

    pbw_sales_decision_at = fields.Datetime(string='Latest Sales Decision', readonly=True, copy=False, index=True)
    pbw_order_review_state = fields.Selection([
        ('none', 'Not Requested'), ('requested', 'Awaiting Sales Order Approval'),
        ('returned', 'Sales Order Request Returned'), ('approved', 'Sales Order Approved'),
        ('direct', 'Directly Confirmed')],
        default='none', string='Sales Order Review', readonly=True, copy=False, tracking=True, index=True)
    pbw_order_requester_id = fields.Many2one('res.users', string='Conversion Requested By', readonly=True, copy=False)
    pbw_order_approver_id = fields.Many2one('res.users', string='Sales Order Approved By', readonly=True, copy=False)
    pbw_direct_confirmed_by_id = fields.Many2one(
        'res.users', string='Directly Confirmed By', readonly=True, copy=False)
    pbw_can_confirm_direct = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_requires_review = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_can_submit = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_can_approve = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_can_return = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_can_request_order = fields.Boolean(compute='_compute_pbw_review_buttons')
    pbw_can_approve_order = fields.Boolean(compute='_compute_pbw_review_buttons')

    def _pbw_sales_owner(self):
        """Original creator, never the salesperson or an all-documents editor.

        Older builds could enroll a native draft under the editor. create_uid
        takes precedence so that historical metadata cannot grant ownership.
        """
        self.ensure_one()
        return self.create_uid or self.pbw_portal_creator_id

    @api.model
    def _pbw_sales_owner_domain(self, user):
        return [('create_uid', '=', user.id)]

    @api.model
    def _pbw_sales_project_field(self):
        """An optional bridge may map the existing construction project field."""
        return 'pbw_project_id'

    def _pbw_sales_project(self):
        self.ensure_one()
        return self[self._pbw_sales_project_field()]

    @api.model
    def _pbw_sales_project_values(self, project):
        return {self._pbw_sales_project_field(): project.id if project else False}

    @api.model
    def _pbw_sales_project_search_domain(self, query):
        return [(self._pbw_sales_project_field() + '.name', 'ilike', query)]

    def _pbw_native_confirmation_context(self):
        """Bridge extension point, called only after operation authorization."""
        self.ensure_one()
        return {}

    def _pbw_after_native_confirmation(self):
        """Optional integration cleanup; no other addon is touched by the base."""
        return True

    def _pbw_is_sales_approver(self, user):
        self.ensure_one()
        return bool(user.active and self.company_id in user.company_ids
            and user.has_group(_PREFIX+'group_portal_sales_approver')
            and not False
            and (not user.share or user.sudo().with_company(user.company_id).employee_id))

    def _pbw_review_permissions(self, user):
        self.ensure_one()
        allowed = bool(user.active and self.company_id in user.company_ids
            and (not user.share or user.sudo().with_company(user.company_id).employee_id))
        creator = allowed and user.has_group(_PREFIX + 'group_portal_sales_creator')
        owner = self._pbw_sales_owner()
        owned = bool(owner and owner == user)
        approver = allowed and user.has_group(_PREFIX + 'group_portal_sales_approver')
        reviewer = bool(approver and self.pbw_portal_creator_id
            and user not in (owner, self.pbw_portal_creator_id, self.pbw_portal_submitter_id))
        draft = self.state in ('draft', 'sent')
        direct = bool(draft and owned and approver)
        # All Company Documents changes visibility/edit scope, not authorship.
        return dict(
            requires_review=bool(self.pbw_portal_creator_id or creator),
            can_confirm_direct=direct,
            can_submit=bool(draft and creator and owned and not direct
                and self.pbw_portal_review_state in ('draft', 'returned')),
            can_approve=bool(draft and reviewer and self.pbw_portal_review_state == 'submitted'),
            can_return=bool(draft and reviewer and self.pbw_portal_review_state in ('submitted', 'approved')),
            can_request_order=bool(draft and creator and owned and not direct
                and self.pbw_portal_review_state == 'approved' and self.pbw_portal_approver_id
                and self.pbw_order_review_state in ('none', 'returned')),
            can_approve_order=bool(draft and reviewer and self.pbw_portal_review_state == 'approved'
                and self.pbw_portal_approver_id and self.pbw_order_review_state == 'requested'
                and self.pbw_order_requester_id and user != self.pbw_order_requester_id))

    @api.depends_context('uid')
    @api.depends('state', 'company_id', 'create_uid', 'pbw_portal_creator_id', 'pbw_portal_submitter_id',
                 'pbw_portal_review_state', 'pbw_portal_approver_id', 'pbw_order_review_state', 'pbw_order_requester_id')
    def _compute_pbw_review_buttons(self):
        for order in self:
            for key, value in order._pbw_review_permissions(self.env.user.sudo(False)).items():
                order['pbw_'+key] = value

    def _pbw_native_review_access(self):
        if not self.env.user.share:
            self.with_user(self.env.user).sudo(False).check_access('write')

    def _pbw_portal_actor(self, role='creator'):
        self.ensure_one()
        user=self.env.user.sudo(False)
        if (not user.active or not user.has_group(_PREFIX+'group_portal_sales_'+role) or
                False or
                (user.share and not user.sudo().with_company(user.company_id).employee_id) or
                self.company_id not in user.company_ids):
            raise AccessError(_('You do not have permission for this sales review operation.'))
        return user

    def _pbw_portal_lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE',[self.id])
        self.invalidate_recordset()

    def _pbw_review_write(self, vals):
        return self.sudo().with_context(_pbw_sales_review_token=_REVIEW_TOKEN).write(vals)

    def _pbw_portal_reviewers(self):
        self.ensure_one()
        return self.env.ref(_PREFIX+'group_portal_sales_approver').sudo().users.filtered(
            lambda u:u.active and u not in (self._pbw_sales_owner(),self.pbw_portal_creator_id,self.pbw_portal_submitter_id,self.pbw_order_requester_id) and self.company_id in u.company_ids
            and not False
            and (not u.share or u.with_company(u.company_id).employee_id))

    @api.model_create_multi
    def create(self, vals_list):
        trusted=self.env.context.get('_pbw_sales_review_token') is _REVIEW_TOKEN
        prepared=self.env.user.has_group(_PREFIX+'group_portal_sales_creator')
        copied=[]
        for vals in vals_list:
            vals=dict(vals)
            if not trusted:
                if (vals.get('pbw_portal_review_state') not in (None,False,'draft') or vals.get('pbw_portal_approver_id')
                        or vals.get('pbw_portal_submitter_id') or vals.get('pbw_order_review_state') not in (None,False,'none')
                        or vals.get('pbw_order_requester_id') or vals.get('pbw_order_approver_id') or vals.get('pbw_sales_decision_at')
                        or vals.get('pbw_direct_confirmed_by_id')):
                    raise AccessError(_('Sales approval can only be recorded through the review actions.'))
                if prepared or vals.get('pbw_portal_creator_id'):
                    if vals.get('state') not in (None,False,'draft','sent'):
                        raise AccessError(_('Create a draft quotation and request independent approval.'))
                    vals['pbw_portal_creator_id']=self.env.uid
            copied.append(vals)
        return super().create(copied)

    @api.model
    def _pbw_portal_sync_salesperson(self):
        orders=self.sudo().search([('pbw_portal_creator_id','!=',False),('state','in',('draft','sent'))])
        for order in orders:
            if order.user_id != order.pbw_portal_creator_id:
                order.sudo().write({'user_id':order.pbw_portal_creator_id.id})
        return True

    def _pbw_portal_notify(self, users, title, message):
        self.ensure_one()
        self.env['pbw.workspace.notification'].sudo()._emit(users, self, 'sales', title, message)
        for user in users.filtered('active'):
            path = '/my/workspace/sales/%s'%self.id if user.share else '/web#id=%s&model=sale.order&view_type=form'%self.id
            body=Markup('<p><strong>%s</strong></p><p>%s</p><p><a href="%s">Open %s</a></p>') % (title,message,path,self.name)
            # Explicit partner recipients generate inbox/email delivery; the activity also
            # keeps outcomes visible to internal preparers after the notification closes.
            actor=self.env.user
            self.sudo().message_post(body=body,partner_ids=user.partner_id.ids,
                author_id=actor.partner_id.id,
                email_from=actor.email_formatted or self.company_id.partner_id.email_formatted or 'Sales <noreply@localhost>',
                message_type='comment',subtype_xmlid='mail.mt_comment')

    def _pbw_portal_close_activities(self):
        self.sudo().activity_ids.filtered(lambda a:a.summary in ('Sales quotation review: %s'%self.name,'Sales order conversion review: %s'%self.name)).action_feedback(feedback=_('Sales review completed.'))

    def _pbw_portal_notify_reviewers(self, conversion=False):
        self.ensure_one()
        users=self._pbw_portal_reviewers()
        if not users:
            raise UserError(_('No independent Sales Approver is available for this company. Ask your administrator to assign one.'))
        self._pbw_portal_notify(users,(_('Sales order conversion %s awaiting approval') if conversion else _('Quotation %s awaiting approval'))%self.name,
            (_('%s requested approval to convert this quotation into a Sales Order.') if conversion else _('%s submitted this quotation for your review.'))%
            (self.pbw_order_requester_id if conversion else self.pbw_portal_submitter_id or self.pbw_portal_creator_id).name)
        for user in users.filtered(lambda u:not u.share and u.has_group('sales_team.group_sale_salesman')):
            self.sudo().activity_schedule('mail.mail_activity_data_todo',user_id=user.id,
                summary=('Sales order conversion review: %s' if conversion else 'Sales quotation review: %s')%self.name,
                note=_('Review the request, then approve or return it.'))

    def _pbw_portal_notify_creator(self,message):
        self.ensure_one()
        self._pbw_review_write({'pbw_sales_decision_at':fields.Datetime.now()})
        users = self.pbw_portal_creator_id | self.pbw_portal_submitter_id | self.pbw_order_requester_id
        self._pbw_portal_notify(users,_('Quotation %s review update')%self.name,message)
        for user in users.filtered(lambda u:u.active and not u.share and u.has_group('sales_team.group_sale_salesman')):
            summary = 'Sales review update: %s'%self.name
            self.sudo().activity_ids.filtered(lambda a:a.summary == summary and a.user_id == user).action_feedback()
            path = '/web#id=%s&model=sale.order&view_type=form'%self.id
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=user.id, summary=summary,
                note=Markup('<p>%s</p><p><a href="%s">Open %s</a></p>') % (message,path,self.name))

    def _pbw_portal_submit(self):
        user=self._pbw_portal_actor()
        self._pbw_portal_lock()
        self._pbw_native_review_access()
        if not self._pbw_review_permissions(user)['can_submit']:
            raise UserError(_('You can submit only quotations you created. Sales Approvers can confirm their own quotations directly.'))
        lines=self.order_line.filtered(lambda l:not l.display_type)
        if not lines or any(l.product_uom_qty<=0 for l in lines):
            raise ValidationError(_('Add at least one line with a positive quantity.'))
        self._pbw_review_write({'pbw_portal_creator_id':user.id,'pbw_portal_submitter_id':user.id,'pbw_portal_review_state':'submitted','pbw_portal_approver_id':False,'pbw_portal_review_note':False, 'pbw_order_review_state':'none',
            'pbw_order_requester_id':False,'pbw_order_approver_id':False})
        self._pbw_portal_notify_reviewers()
        return True

    def action_pbw_portal_submit(self):
        if self.env.user.share:
            raise AccessError(_('Submit through the sales portal.'))
        self.check_access('write')
        for order in self:order._pbw_portal_submit()
        return {'type':'ir.actions.client','tag':'reload'}

    def action_pbw_portal_approve(self):
        for order in self:
            user=order._pbw_portal_actor('approver');order._pbw_portal_lock()
            order._pbw_native_review_access()
            if (not order.pbw_portal_creator_id or order.pbw_portal_review_state!='submitted' or
                    order.state not in ('draft','sent') or user in (order._pbw_sales_owner(),order.pbw_portal_creator_id,order.pbw_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted quotation can be approved.'))
            order._pbw_review_write({'pbw_portal_review_state':'approved','pbw_portal_approver_id':user.id})
            order._pbw_portal_close_activities()
            order._pbw_portal_notify_creator(_('Approved by %s. The quotation can now be printed. Request Sales Order approval when ready to convert it.')%user.name)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_pbw_portal_return(self):
        for order in self:
            user=order._pbw_portal_actor('approver');order._pbw_portal_lock()
            order._pbw_native_review_access()
            if (not order.pbw_portal_creator_id or order.pbw_portal_review_state not in ('submitted','approved') or
                    order.state not in ('draft','sent') or user in (order._pbw_sales_owner(),order.pbw_portal_creator_id,order.pbw_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted or approved quotation can be returned.'))
            note=(order.pbw_portal_review_note or '').strip()
            if not note:raise ValidationError(_('Explain the correction required.'))
            order._pbw_review_write({'pbw_portal_review_state':'returned','pbw_portal_approver_id':False, 'pbw_order_review_state':'none',
                'pbw_order_approver_id':False})
            order._pbw_portal_close_activities()
            order._pbw_portal_notify_creator(_('Returned for correction: %s')%note)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_pbw_request_order(self):
        for order in self:
            user=order._pbw_portal_actor();order._pbw_portal_lock()
            order._pbw_native_review_access()
            if not order._pbw_review_permissions(user)['can_request_order']:
                raise UserError(_('Only an approved quotation can be submitted for Sales Order approval.'))
            order._pbw_review_write({'pbw_order_review_state':'requested','pbw_order_requester_id':user.id,
                'pbw_order_approver_id':False,'pbw_portal_review_note':False})
            order._pbw_portal_notify_reviewers(conversion=True)
        return {'type':'ir.actions.client','tag':'reload'}

    def action_pbw_approve_order(self):
        for order in self:
            user=order._pbw_portal_actor('approver');order._pbw_portal_lock()
            order._pbw_native_review_access()
            if not order._pbw_review_permissions(user)['can_approve_order']:
                raise UserError(_('Only an independent approver can approve a pending Sales Order request.'))
            # Confirmation and approval share this transaction; native validation failure
            # rolls back the decision, activities and notifications together.
            order.with_company(order.company_id).with_context(
                **dict(order._pbw_native_confirmation_context(),
                       _pbw_sales_confirm_token=_REVIEW_TOKEN, validate_analytic=True)).action_confirm()
            if order.state not in ('sale','done'):
                raise UserError(_('Sales Order confirmation did not complete. Resolve the native validation first.'))
            order._pbw_review_write({'pbw_order_review_state':'approved','pbw_order_approver_id':user.id})
            order._pbw_portal_close_activities()
            order._pbw_after_native_confirmation()
            order._pbw_portal_notify_creator(_('Sales Order conversion approved by %s. %s is now a Sales Order.')%(user.name,order.name))
        return {'type':'ir.actions.client','tag':'reload'}

    def action_pbw_return_order(self):
        for order in self:
            user=order._pbw_portal_actor('approver');order._pbw_portal_lock()
            order._pbw_native_review_access()
            if not order._pbw_review_permissions(user)['can_approve_order']:
                raise UserError(_('Only an independent approver can return a pending Sales Order request.'))
            note=(order.pbw_portal_review_note or '').strip()
            if not note:raise ValidationError(_('Explain the correction required in Review Notes.'))
            order._pbw_review_write({'pbw_order_review_state':'returned','pbw_order_approver_id':False})
            order._pbw_portal_close_activities()
            order._pbw_portal_notify_creator(_('Sales Order request returned: %s')%note)
        return {'type':'ir.actions.client','tag':'reload'}

    def _pbw_portal_can_confirm(self, user):
        return self._pbw_review_permissions(user)['can_confirm_direct']

    def action_confirm(self):
        actor = self.env.user.sudo(False)
        if self.env.context.get('_pbw_sales_confirm_token') is _REVIEW_TOKEN:
            return super().action_confirm()
        if actor.share and not self.env.su:
            raise AccessError(_('Confirm through the Sales workspace.'))
        managed = self.filtered(lambda order: bool(order.pbw_portal_creator_id)
            or actor.has_group(_PREFIX + 'group_portal_sales_creator'))
        # Check the whole batch before applying any confirmation.
        for order in managed:
            if not order._pbw_portal_can_confirm(actor):
                raise UserError(_('Request Sales Order approval. Only a Sales Approver may directly confirm a quotation they created.'))
        for order in managed:
            order._pbw_confirm_own_quotation()
        unmanaged = self - managed
        return super(SaleOrder, unmanaged).action_confirm() if unmanaged else True

    def _pbw_confirm_own_quotation(self):
        self.ensure_one()
        user = self._pbw_portal_actor('approver')
        # A savepoint keeps confirmation, audit metadata and notification cleanup
        # atomic even when a caller catches a native validation exception.
        with self.env.cr.savepoint():
            self._pbw_portal_lock()
            self._pbw_native_review_access()
            if not self._pbw_review_permissions(user)['can_confirm_direct']:
                raise AccessError(_('Only a Sales Approver can directly confirm their own draft quotation.'))
            lines = self.order_line.filtered(lambda line: not line.display_type)
            if not lines or any(line.product_uom_qty <= 0 for line in lines):
                raise ValidationError(_('Add at least one line with a positive quantity.'))
            context = dict(self._pbw_native_confirmation_context(),
                _pbw_sales_confirm_token=_REVIEW_TOKEN, validate_analytic=True)
            self.with_company(self.company_id).with_context(**context).action_confirm()
            if self.state not in ('sale', 'done'):
                raise UserError(_('Sales Order confirmation did not complete. Resolve the native validation first.'))
            # Direct confirmation is not recorded as an independent approval.
            self._pbw_review_write({'pbw_portal_creator_id': user.id,
                'pbw_order_review_state': 'direct', 'pbw_direct_confirmed_by_id': user.id})
            self._pbw_portal_close_activities()
            self._pbw_after_native_confirmation()
            self.sudo().message_post(
                body=_('Directly confirmed by %s as the quotation creator and Sales Approver; no independent approval was required.') % user.name,
                author_id=user.partner_id.id, message_type='comment', subtype_xmlid='mail.mt_note')
        return True

    def action_pbw_confirm_own(self):
        if self.env.user.share and not self.env.su:
            raise AccessError(_('Confirm through the Sales workspace.'))
        for order in self:
            order._pbw_confirm_own_quotation()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _pbw_portal_invalidate_review(self):
        if self.env.context.get('_pbw_sales_confirm_token') is _REVIEW_TOKEN:
            return
        for order in self.sorted('id'):
            # An approver edits as part of review. Only the explicit Return
            # action sends the quotation back; never infer a return from a save.
            if order._pbw_is_sales_approver(self.env.user.sudo(False)):
                continue
            if order.pbw_portal_creator_id and order.state in ('draft','sent') and order.pbw_portal_review_state in ('submitted','approved'):
                order._pbw_portal_lock()
                order._pbw_review_write({'pbw_portal_review_state':'returned','pbw_portal_approver_id':False,
                    'pbw_order_review_state':'none', 'pbw_order_requester_id':False,'pbw_order_approver_id':False,
                    'pbw_portal_review_note':_('Quotation contents changed. Check and resubmit for approval.')})
                order._pbw_portal_close_activities()

    def write(self,vals):
        if vals.get('state')=='sale' and self.env.context.get('_pbw_sales_confirm_token') is not _REVIEW_TOKEN:
            if self.filtered('pbw_portal_creator_id') or self.env.user.has_group(_PREFIX+'group_portal_sales_creator'):
                raise AccessError(_('Request Sales Order approval; the approver confirms the conversion.'))
        if _REVIEW_FIELDS.intersection(vals) and self.env.context.get('_pbw_sales_review_token') is not _REVIEW_TOKEN:
            raise AccessError(_('Sales approval metadata can only be changed through the review actions.'))
        content={'date_order','partner_id','company_id','currency_id','pricelist_id','payment_term_id','validity_date','order_line','note',
                 'pbw_project_id', self._pbw_sales_project_field()}
        if content.intersection(vals):self._pbw_portal_invalidate_review()
        return super().write(vals)

    def action_draft(self):
        result=super().action_draft()
        self.filtered('pbw_portal_creator_id')._pbw_review_write({'pbw_portal_review_state':'draft','pbw_portal_approver_id':False,'pbw_portal_review_note':False, 'pbw_order_review_state':'none',
            'pbw_order_requester_id':False,'pbw_order_approver_id':False,'pbw_direct_confirmed_by_id':False})
        return result


class SaleOrderLine(models.Model):
    _inherit='sale.order.line'

    @api.model_create_multi
    def create(self,vals_list):
        self.env['sale.order'].browse(list({v['order_id'] for v in vals_list if v.get('order_id')}))._pbw_portal_invalidate_review()
        return super().create(vals_list)

    def write(self,vals):
        if {'product_id','name','product_uom_qty','price_unit','discount','tax_id','product_uom','display_type','analytic_distribution'}.intersection(vals):
            self.order_id._pbw_portal_invalidate_review()
        return super().write(vals)

    def unlink(self):
        self.order_id._pbw_portal_invalidate_review()
        return super().unlink()
