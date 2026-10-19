import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)
_PREFIX = 'absar_portal_sales.'
_REVIEW_TOKEN = object()
_REVIEW_FIELDS = {'absar_portal_creator_id','absar_portal_submitter_id','absar_portal_review_state','absar_portal_approver_id'}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    absar_portal_creator_id = fields.Many2one('res.users', string='Prepared By', readonly=True, index=True, copy=False)
    absar_portal_submitter_id = fields.Many2one('res.users',string='Submitted By',readonly=True,copy=False)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved for Sending'), ('returned', 'Returned for Correction')],
        string='Sales Review', default='draft', copy=False, tracking=True, index=True)
    absar_portal_review_note = fields.Text(string='Review Notes', copy=False)
    absar_portal_approver_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)

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
            lambda u:u.active and u not in (self.absar_portal_creator_id,self.absar_portal_submitter_id) and self.company_id in u.company_ids
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
                if vals.get('absar_portal_review_state') not in (None,False,'draft') or vals.get('absar_portal_approver_id'):
                    raise AccessError(_('Sales approval can only be recorded through the review actions.'))
                if prepared or vals.get('absar_portal_creator_id'):
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
        body=Markup('<p><strong>%s</strong></p><p>%s</p>') % (title,message)
        self.sudo().message_post(body=body,partner_ids=users.partner_id.ids,message_type='comment',subtype_xmlid='mail.mt_comment')
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
        self.sudo().activity_ids.filtered(lambda a:a.summary=='Sales quotation review: %s'%self.name).action_feedback(feedback=_('Sales review completed.'))

    def _absar_portal_notify_reviewers(self):
        self.ensure_one()
        users=self._absar_portal_reviewers()
        if not users:
            raise UserError(_('No independent Sales Approver is available for this company. Ask your administrator to assign one.'))
        self._absar_portal_notify(users,_('Quotation %s awaiting approval')%self.name,
            _('%s submitted this quotation for your review.')%(self.absar_portal_submitter_id or self.absar_portal_creator_id).name)
        for user in users.filtered(lambda u:not u.share and u.has_group('sales_team.group_sale_salesman')):
            self.sudo().activity_schedule('mail.mail_activity_data_todo',user_id=user.id,
                summary='Sales quotation review: %s'%self.name,
                note=_('Review, approve for sending, or return this quotation.'))

    def _absar_portal_notify_creator(self,message):
        self.ensure_one()
        if self.absar_portal_creator_id:
            self._absar_portal_notify(self.absar_portal_creator_id,_('Quotation %s review update')%self.name,message)

    def _absar_portal_submit(self):
        user=self._absar_portal_actor()
        self._absar_portal_lock()
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
        self._absar_review_write({'absar_portal_creator_id':self.absar_portal_creator_id.id or user.id,'absar_portal_submitter_id':user.id,'absar_portal_review_state':'submitted','absar_portal_approver_id':False,'absar_portal_review_note':False})
        self._absar_portal_notify_reviewers()
        return True

    def action_absar_portal_submit(self):
        if self.env.user.share:
            raise AccessError(_('Submit through the sales portal.'))
        self.check_access('write')
        for order in self:order._absar_portal_submit()
        return True

    def action_absar_portal_approve(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            if (not order.absar_portal_creator_id or order.absar_portal_review_state!='submitted' or
                    order.state not in ('draft','sent') or user in (order.absar_portal_creator_id,order.absar_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted quotation can be approved.'))
            order._absar_review_write({'absar_portal_review_state':'approved','absar_portal_approver_id':user.id})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Approved by %s. The quotation can now be printed and confirmed.')%user.name)
        return True

    def action_absar_portal_return(self):
        for order in self:
            user=order._absar_portal_actor('approver');order._absar_portal_lock()
            if (not order.absar_portal_creator_id or order.absar_portal_review_state not in ('submitted','approved') or
                    order.state not in ('draft','sent') or user in (order.absar_portal_creator_id,order.absar_portal_submitter_id)):
                raise UserError(_('Only another employee’s submitted or approved quotation can be returned.'))
            note=(order.absar_portal_review_note or '').strip()
            if not note:raise ValidationError(_('Explain the correction required.'))
            order._absar_review_write({'absar_portal_review_state':'returned','absar_portal_approver_id':False})
            order._absar_portal_close_activities()
            order._absar_portal_notify_creator(_('Returned for correction: %s')%note)
        return True

    def _absar_portal_can_confirm(self,user):
        self.ensure_one()
        return bool(user.has_group(_PREFIX+'group_portal_sales_creator') and
            not user.has_group('employee_portal_suite.group_attendance_only') and self.company_id in user.company_ids and
            (not user.share or user.sudo().with_company(user.company_id).employee_id) and
            (user.has_group(_PREFIX+'group_portal_sales_user') or user.has_group(_PREFIX+'group_portal_sales_approver') or self.absar_portal_creator_id==user) and
            self.state in ('draft','sent') and self.absar_portal_creator_id and
            self.absar_portal_review_state=='approved' and self.absar_portal_approver_id and self.absar_portal_approver_id not in (self.absar_portal_creator_id,self.absar_portal_submitter_id))

    def action_confirm(self):
        actor=self.env.user.sudo(False)
        for order in self:
            if order.absar_portal_creator_id or actor.has_group(_PREFIX+'group_portal_sales_creator'):
                order._absar_portal_lock()
                if not order._absar_portal_can_confirm(actor):
                    raise UserError(_('Submit the quotation and obtain independent Sales approval before confirmation.'))
        return super(SaleOrder,self.with_context(_absar_sales_confirm_token=_REVIEW_TOKEN)).action_confirm()

    def _absar_portal_invalidate_review(self):
        for order in self.sorted('id'):
            if order.absar_portal_creator_id and order.state in ('draft','sent') and order.absar_portal_review_state in ('submitted','approved'):
                order._absar_portal_lock()
                order._absar_review_write({'absar_portal_review_state':'returned','absar_portal_approver_id':False,
                    'absar_portal_review_note':_('Quotation contents changed. Check and resubmit for approval.')})
                order._absar_portal_close_activities()

    def write(self,vals):
        if vals.get('state')=='sale' and self.env.context.get('_absar_sales_confirm_token') is not _REVIEW_TOKEN and not self.env.su:
            if self.filtered('absar_portal_creator_id') or self.env.user.has_group(_PREFIX+'group_portal_sales_creator'):
                raise AccessError(_('Use Confirm after independent Sales approval.'))
        if _REVIEW_FIELDS.intersection(vals) and self.env.context.get('_absar_sales_review_token') is not _REVIEW_TOKEN:
            raise AccessError(_('Sales approval metadata can only be changed through the review actions.'))
        content={'partner_id','company_id','currency_id','pricelist_id','payment_term_id','validity_date','order_line','note',
                 'construction_project_id','absar_proposal_type','absar_proposal_title','absar_proposal_section_ids','absar_proposal_payment_ids'}
        if content.intersection(vals):self._absar_portal_invalidate_review()
        return super().write(vals)

    def action_draft(self):
        result=super().action_draft()
        self.filtered('absar_portal_creator_id')._absar_review_write({'absar_portal_review_state':'draft','absar_portal_approver_id':False,'absar_portal_review_note':False})
        return result


class SaleOrderLine(models.Model):
    _inherit='sale.order.line'

    @api.model_create_multi
    def create(self,vals_list):
        self.env['sale.order'].browse(list({v['order_id'] for v in vals_list if v.get('order_id')}))._absar_portal_invalidate_review()
        return super().create(vals_list)

    def write(self,vals):
        if {'product_id','name','product_uom_qty','price_unit','discount','tax_id','product_uom','display_type'}.intersection(vals):
            self.order_id._absar_portal_invalidate_review()
        return super().write(vals)

    def unlink(self):
        self.order_id._absar_portal_invalidate_review()
        return super().unlink()
