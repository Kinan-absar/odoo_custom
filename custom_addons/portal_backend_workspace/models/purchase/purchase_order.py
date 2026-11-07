import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)
PREFIX = 'portal_backend_workspace.purchase__'
_CONFIRM_TOKEN=object()


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Retained for upgrade compatibility; new forms use actual project_id.
    pbw_portal_project_id = fields.Many2one('project.project', string='Portal Project (Legacy)', check_company=True)
    pbw_portal_working_order = fields.Boolean(readonly=True, copy=False, default=False)
    pbw_portal_requires_review = fields.Boolean(compute='_compute_pbw_purchase_requires_review')
    pbw_portal_all_documents = fields.Boolean(compute='_compute_pbw_purchase_requires_review')

    @api.depends('pbw_portal_preparer_id','pbw_portal_working_order')
    @api.depends_context('uid')
    def _compute_pbw_purchase_requires_review(self):
        enrolled=self.env.user.has_group(PREFIX+'group_portal_purchase_preparer')
        all_documents=self.env.user.has_group(PREFIX+'group_portal_purchase_user')
        for po in self:
            po.pbw_portal_all_documents=all_documents
            po.pbw_portal_requires_review=bool(po.pbw_portal_preparer_id or po.pbw_portal_working_order or enrolled)

    pbw_portal_preparer_id = fields.Many2one('res.users', string='Issuer', readonly=True, copy=False, index=True)
    pbw_portal_submitter_id = fields.Many2one('res.users',string='Submitted By',readonly=True,copy=False)
    pbw_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved'), ('returned', 'Returned for Correction')],
        default='draft', string='Purchase Review Status', copy=False, tracking=True, index=True)
    pbw_portal_review_note = fields.Text('Review Note', copy=False)
    pbw_portal_approver_id = fields.Many2one('res.users', readonly=True, copy=False)
    pbw_portal_approved_on = fields.Datetime(readonly=True, copy=False)

    pbw_portal_reviewer_ids = fields.Many2many(
        'res.users', string='Eligible Approvers', compute='_compute_pbw_purchase_reviewers', compute_sudo=True)

    @api.depends('company_id', 'pbw_portal_preparer_id', 'pbw_portal_submitter_id', 'user_id')
    def _compute_pbw_purchase_reviewers(self):
        for po in self:
            po.pbw_portal_reviewer_ids = po._pbw_purchase_reviewers()

    def _pbw_purchase_reviewers(self):
        self.ensure_one()
        issuer = self.pbw_portal_preparer_id or self.user_id
        return self.env.ref(PREFIX + 'group_portal_purchase_approver').sudo().users.filtered(
            lambda u: u.active and not False and
            (not u.share or u.with_company(u.company_id).employee_id) and u != issuer and u != self.pbw_portal_submitter_id and self.company_id in u.company_ids)

    def _pbw_purchase_actor(self, role):
        user = self.env.user.sudo(False)
        if (not user.active or (user.share and not user.sudo().with_company(user.company_id).employee_id) or
                False or
                not user.has_group(PREFIX + 'group_portal_purchase_' + role)):
            raise AccessError(_('You do not have the required purchase workspace permission.'))
        return user

    def _pbw_purchase_approver(self):
        return self._pbw_purchase_actor('approver')

    def _pbw_purchase_lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM purchase_order WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _pbw_purchase_check_company(self, user):
        self.ensure_one()
        if self.company_id not in user.company_ids:
            raise AccessError(_('This company is not available to you.'))

    def _pbw_purchase_editable(self, user):
        self.ensure_one()
        return bool(user.has_group(PREFIX + 'group_portal_purchase_preparer') and
                    not False and
                    self.company_id in user.company_ids and (user in (self.pbw_portal_preparer_id,self.pbw_portal_submitter_id) or user.has_group(PREFIX+'group_portal_purchase_user')) and
                    self.state in ('draft', 'sent') and
                    self.pbw_portal_review_state in (False, 'draft', 'returned'))

    def _pbw_purchase_notify(self, users, title, note):
        self.ensure_one()
        self.env['pbw.workspace.notification'].sudo()._emit(users, self, 'purchase', title, note)
        users = users.filtered(lambda u: u.active and self.company_id in u.company_ids)
        body = Markup('<p><strong>%s</strong></p><p>%s</p>') % (title, note)
        self.sudo().message_post(body=body, partner_ids=users.partner_id.ids,
                                 message_type='comment', subtype_xmlid='mail.mt_comment')

    def _pbw_purchase_close_activities(self):
        activities = self.sudo().activity_ids.filtered(
            lambda a: a.summary in ('Portal RFQ review: %s' % self.name, 'Purchase order review: %s' % self.name) and
            a.activity_type_id == self.env.ref('mail.mail_activity_data_todo'))
        activities.action_feedback(feedback=_('Portal review completed.'))

    def _pbw_purchase_submit(self):
        user = self._pbw_purchase_actor('preparer')
        self._pbw_purchase_lock()
        if not self._pbw_purchase_editable(user):
            raise UserError(_('Only an accessible editable draft RFQ can be submitted.'))
        lines = self.order_line.filtered(lambda l: not l.display_type)
        if not lines or any(not l.product_id or l.product_qty <= 0 for l in lines):
            raise ValidationError(_('Add at least one product with a positive quantity.'))
        if any(not l.date_planned for l in lines):
            raise ValidationError(_('Expected arrival is required for every product line.'))
        # The analytic mixin enforces applicability per plan with this context.
        if hasattr(lines, '_validate_analytic_distribution'):
            lines.with_context(validate_analytic=True)._validate_analytic_distribution()
        # The submitting employee is accountable even when an all-document
        # user prepares another buyer's draft. No working role bypasses review.
        self.sudo().write({'pbw_portal_preparer_id':self.pbw_portal_preparer_id.id or user.id,
                           'pbw_portal_submitter_id':user.id,'pbw_portal_working_order':False})
        reviewers = self._pbw_purchase_reviewers()
        if not reviewers:
            raise UserError(_('No independent Purchase Approver is available for this company. Save as a draft and ask your administrator to assign one.'))
        self.sudo().write({'pbw_portal_review_state': 'submitted',
                           'pbw_portal_review_note': False,
                           'pbw_portal_approver_id': False, 'pbw_portal_approved_on': False})
        self._pbw_purchase_notify(reviewers, _('Purchase order %s awaiting approval') % self.name,
                            _('%s submitted a purchase order for your approval.') % user.name)
        for reviewer in reviewers.filtered(lambda u: not u.share):
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=reviewer.id,
                                         summary='Purchase order review: %s' % self.name)

    def action_pbw_portal_approve(self):
        """One approval action completes the native PO confirmation chain."""
        user = self._pbw_purchase_approver()
        for po in self.sorted('id'):
            po._pbw_purchase_lock()
            po._pbw_purchase_check_company(user)
            if (not po.pbw_portal_preparer_id or
                    user in (po.pbw_portal_preparer_id, po.pbw_portal_submitter_id) or
                    po.pbw_portal_review_state not in ('submitted', 'approved') or
                    po.state not in ('draft', 'sent')):
                raise UserError(_('Only another issuer’s submitted purchase order can be approved.'))
            # Older releases could leave an approved draft. The same Approve
            # action finishes that draft after validating the independent actor.
            po.sudo().write({'pbw_portal_review_state': 'approved',
                             'pbw_portal_approver_id': user.id,
                             'pbw_portal_approved_on': fields.Datetime.now()})
            result = po.sudo().with_company(po.company_id).with_context(
                validate_analytic=True, _pbw_purchase_approval_token=_CONFIRM_TOKEN
            ).button_confirm()
            if isinstance(result, dict) or po.state not in ('purchase', 'done'):
                raise UserError(_('Purchase approval could not complete confirmation. No approval was saved; resolve the installed purchase workflow and retry.'))
            po._pbw_purchase_close_activities()
            po._pbw_purchase_notify(po.pbw_portal_preparer_id, _('Purchase order %s approved') % po.name,
                              _('Approved by %s.') % user.name)
        return True

    def action_pbw_portal_approve_confirm(self):
        # Compatibility for cached portal pages and old backend actions.
        return self.action_pbw_portal_approve()

    def _approval_allowed(self):
        self.ensure_one()
        if (self.env.context.get('_pbw_purchase_approval_token') is _CONFIRM_TOKEN and
                self.pbw_portal_review_state == 'approved' and self.pbw_portal_approver_id):
            # Independent review is the single approval level for managed POs.
            # Native receipt creation and installed confirmation hooks still run.
            return True
        return super()._approval_allowed()

    def action_pbw_portal_return(self):
        user = self._pbw_purchase_approver()
        for po in self:
            po._pbw_purchase_lock()
            po._pbw_purchase_check_company(user)
            if (not po.pbw_portal_preparer_id or user in (po.pbw_portal_preparer_id,po.pbw_portal_submitter_id) or
                    po.pbw_portal_review_state not in ('submitted', 'approved') or
                    po.state not in ('draft', 'sent')):
                raise UserError(_('Only another preparer’s unconfirmed submitted or approved RFQ can be returned.'))
            if not (po.pbw_portal_review_note or '').strip():
                raise ValidationError(_('Please explain the correction required.'))
            po.sudo().write({'pbw_portal_review_state': 'returned',
                             'pbw_portal_approver_id': False, 'pbw_portal_approved_on': False})
            po._pbw_purchase_close_activities()
            po._pbw_purchase_notify(po.pbw_portal_preparer_id, _('Purchase order %s returned') % po.name,
                              po.pbw_portal_review_note)
        return True

    def action_pbw_portal_confirm(self):
        # Legacy confirmation links use the same independent approval action.
        return self.action_pbw_portal_approve()

    def action_pbw_portal_submit(self):
        """Native Purchase entry point; the portal uses its scoped controller."""
        user = self._pbw_purchase_actor('preparer')
        if user.share:
            raise AccessError(_('Submit this request through the purchase portal.'))
        self.check_access('write')
        for po in self.sorted('id'):
            po._pbw_purchase_lock()
            po._pbw_purchase_check_company(user)
            if po.state not in ('draft', 'sent'):
                raise UserError(_('Only an RFQ can be submitted for approval.'))
            if not po.pbw_portal_preparer_id:
                # An internal issuer adopts only their own native RFQ. Never
                # claim another buyer's draft or change existing review history.
                if (not user.has_group(PREFIX+'group_portal_purchase_user') and
                        ((po.user_id and po.user_id != user) or (not po.user_id and po.create_uid != user))):
                    raise UserError(_('Only the assigned buyer can submit this RFQ.'))
                po.sudo().write({'pbw_portal_preparer_id': user.id, 'user_id': user.id})
            po._pbw_purchase_submit()
        return True

    def button_confirm(self):
        managed=self.filtered('pbw_portal_requires_review')
        if not managed:
            return super(PurchaseOrder,self.with_context(_pbw_purchase_confirm_token=_CONFIRM_TOKEN)).button_confirm()
        if managed!=self:
            raise UserError(_('Confirm review-managed and ordinary native orders separately.'))
        rfqs = self.filtered(lambda po: po.state in ('draft', 'sent'))
        pending = rfqs.filtered(lambda po: not po.pbw_portal_preparer_id or
                                po.pbw_portal_review_state != 'approved')
        if pending:
            if pending != rfqs or len(rfqs) != len(self):
                raise UserError(_('Submit pending RFQs separately from approved orders.'))
            # Also guard the original method used by RPC and existing actions:
            # changing a button label alone must never allow direct confirmation.
            return pending.action_pbw_portal_submit()
        for po in rfqs:
            user = po._pbw_purchase_approver()
            po._pbw_purchase_lock()
            po._pbw_purchase_check_company(user)
            if (not po.pbw_portal_approver_id or
                    user in (po.pbw_portal_preparer_id,po.pbw_portal_submitter_id) or
                    po.pbw_portal_approver_id == po.pbw_portal_preparer_id):
                raise UserError(_('This RFQ must be independently approved before confirmation.'))
        return super(PurchaseOrder,self.with_context(_pbw_purchase_confirm_token=_CONFIRM_TOKEN)).button_confirm()

    def button_approve(self, force=False):
        for po in self:
            if not po.pbw_portal_requires_review:
                continue
            if po.state not in ('draft', 'sent', 'to approve'):
                continue
            user = po._pbw_purchase_approver()
            po._pbw_purchase_lock()
            po._pbw_purchase_check_company(user)
            if (not po.pbw_portal_preparer_id or po.pbw_portal_review_state != 'approved' or
                    not po.pbw_portal_approver_id or user in (po.pbw_portal_preparer_id,po.pbw_portal_submitter_id) or
                    po.pbw_portal_approver_id == po.pbw_portal_preparer_id):
                raise UserError(_('Independent purchase review approval is required first.'))
        return super(PurchaseOrder,self.with_context(_pbw_purchase_confirm_token=_CONFIRM_TOKEN)).button_approve(force=force)

    def _pbw_purchase_invalidate_review(self):
        for po in self.sorted('id'):
            if po.pbw_portal_preparer_id and po.state in ('draft', 'sent', 'to approve'):
                po._pbw_purchase_lock()
                if po.pbw_portal_review_state in ('approved', 'submitted'):
                    po.sudo().write({
                        'pbw_portal_review_state': 'returned',
                        'pbw_portal_approver_id': False,
                        'pbw_portal_approved_on': False,
                        'pbw_portal_review_note': _('Purchase order contents changed. Please check and resubmit for approval.'),
                    })
                    po._pbw_purchase_close_activities()

    def write(self, vals):
        if vals.get('state') in ('purchase','done') and not self.env.su and self.env.context.get('_pbw_purchase_confirm_token') is not _CONFIRM_TOKEN:
            if any(po.state not in ('purchase','done') for po in self):
                raise AccessError(_('Use independent Purchase approval and confirmation.'))
        metadata={'pbw_portal_preparer_id','pbw_portal_submitter_id','pbw_portal_review_state','pbw_portal_approver_id','pbw_portal_approved_on'}
        if metadata.intersection(vals) and not self.env.su:
            raise AccessError(_('Purchase approval metadata can only be changed through the review actions.'))
        content_fields = {'partner_id', 'partner_ref', 'project_id', 
                          'currency_id', 'company_id', 'date_order', 'date_planned', 'notes',
                          'payment_term_id', 'fiscal_position_id', 'incoterm_id',
                          'incoterm_location', 'picking_type_id', 'order_line', 'origin'}
        if content_fields.intersection(vals):
            self._pbw_purchase_invalidate_review()
        return super().write(vals)

    def button_draft(self):
        result = super().button_draft()
        self.filtered('pbw_portal_preparer_id').sudo().write({
            'pbw_portal_review_state': 'draft', 'pbw_portal_approver_id': False,
            'pbw_portal_approved_on': False, 'pbw_portal_review_note': False})
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    pbw_expense_account_id = fields.Many2one('account.account', string='Portal Expense Account', check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['purchase.order'].browse(list({v['order_id'] for v in vals_list if v.get('order_id')}))
        orders._pbw_purchase_invalidate_review()
        return super().create(vals_list)

    def write(self, vals):
        content_fields = {'product_id', 'name', 'product_qty', 'product_uom', 'price_unit',
                          'discount', 'taxes_id', 'analytic_distribution', 'date_planned',
                          'pbw_expense_account_id', 'display_type', 'sequence', 'order_id'}
        if content_fields.intersection(vals):
            self.order_id._pbw_purchase_invalidate_review()
        return super().write(vals)

    def unlink(self):
        self.order_id._pbw_purchase_invalidate_review()
        return super().unlink()

    def _prepare_account_move_line(self, move=False):
        vals = super()._prepare_account_move_line(move=move)
        if self.pbw_expense_account_id:
            account = self.pbw_expense_account_id
            if account.deprecated or self.company_id not in account.company_ids:
                raise ValidationError(_('The selected expense account is unavailable for this company.'))
            fiscal_position = move.fiscal_position_id if move else self.order_id.fiscal_position_id
            vals['account_id'] = (fiscal_position.map_account(account) if fiscal_position else account).id
        return vals
