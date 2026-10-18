import logging
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)
PREFIX = 'absar_portal_purchase_monitor.'


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # Retained for upgrade compatibility; new forms use actual project_id.
    absar_portal_project_id = fields.Many2one('project.project', string='Portal Project (Legacy)', check_company=True)
    absar_portal_preparer_id = fields.Many2one('res.users', string='Issuer', readonly=True, copy=False, index=True)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Draft'), ('submitted', 'Awaiting Approval'),
        ('approved', 'Approved'), ('returned', 'Returned for Correction')],
        default='draft', string='Purchase Review Status', copy=False, tracking=True, index=True)
    absar_portal_review_note = fields.Text('Review Note', copy=False)
    absar_portal_approver_id = fields.Many2one('res.users', readonly=True, copy=False)
    absar_portal_approved_on = fields.Datetime(readonly=True, copy=False)

    def _portal_actor(self, role):
        user = self.env.user.sudo(False)
        if (not user.active or (user.share and not user.sudo().employee_id) or
                user.has_group('employee_portal_suite.group_attendance_only') or
                not user.has_group(PREFIX + 'group_portal_purchase_' + role)):
            raise AccessError(_('You do not have the required purchase workspace permission.'))
        return user

    def _portal_approver(self):
        return self._portal_actor('approver')

    def _portal_lock(self):
        self.ensure_one()
        self.env.cr.execute('SELECT id FROM purchase_order WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _portal_check_company(self, user):
        self.ensure_one()
        if self.company_id not in user.company_ids:
            raise AccessError(_('This company is not available to you.'))

    def _portal_editable(self, user):
        self.ensure_one()
        return bool(user.has_group(PREFIX + 'group_portal_purchase_preparer') and
                    not user.has_group('employee_portal_suite.group_attendance_only') and
                    self.company_id in user.company_ids and self.absar_portal_preparer_id == user and
                    self.state in ('draft', 'sent') and
                    self.absar_portal_review_state in (False, 'draft', 'returned'))

    def _portal_notify(self, users, title, note):
        self.ensure_one()
        users = users.filtered(lambda u: u.active and self.company_id in u.company_ids)
        body = Markup('<p><strong>%s</strong></p><p>%s</p>') % (title, note)
        self.sudo().message_post(body=body, partner_ids=users.partner_id.ids,
                                 message_type='comment', subtype_xmlid='mail.mt_comment')
        if 'employee.portal.webpush.service' in self.env:
            for user in users:
                # Optional delivery failure must not roll back a valid approval.
                try:
                    with self.env.cr.savepoint():
                        self.env['employee.portal.webpush.service'].sudo().send_to_user(
                            user, title, note,
                            path='/my/employee/purchase/%s' % self.id if user.share else
                            '/web#id=%s&model=purchase.order&view_type=form' % self.id,
                            tag='purchase-%s' % self.id)
                except Exception:
                    _logger.warning('Optional purchase webpush failed for order %s', self.id, exc_info=True)

    def _portal_close_activities(self):
        activities = self.sudo().activity_ids.filtered(
            lambda a: a.summary == 'Portal RFQ review: %s' % self.name and
            a.activity_type_id == self.env.ref('mail.mail_activity_data_todo'))
        activities.action_feedback(feedback=_('Portal review completed.'))

    def _portal_submit(self):
        user = self._portal_actor('preparer')
        self._portal_lock()
        if not self._portal_editable(user):
            raise UserError(_('Only your own editable draft RFQ can be submitted.'))
        lines = self.order_line.filtered(lambda l: not l.display_type)
        if not lines or any(not l.product_id or l.product_qty <= 0 for l in lines):
            raise ValidationError(_('Add at least one product with a positive quantity.'))
        if any(not l.date_planned for l in lines):
            raise ValidationError(_('Expected arrival is required for every product line.'))
        # The analytic mixin enforces applicability per plan with this context.
        if hasattr(lines, '_validate_analytic_distribution'):
            lines.with_context(validate_analytic=True)._validate_analytic_distribution()
        group = self.env.ref(PREFIX + 'group_portal_purchase_approver')
        reviewers = group.sudo().users.filtered(
            lambda u: u.active and not u.has_group('employee_portal_suite.group_attendance_only') and (not u.share or u.employee_id) and u != user and self.company_id in u.company_ids)
        if not reviewers:
            raise UserError(_('No independent Purchase Approver is available for this company. Save as a draft and ask your administrator to assign one.'))
        self.sudo().write({'absar_portal_review_state': 'submitted',
                           'absar_portal_review_note': False,
                           'absar_portal_approver_id': False, 'absar_portal_approved_on': False})
        self._portal_notify(reviewers, _('RFQ %s awaiting your confirmation') % self.name,
                            _('%s requests your approval and confirmation in Purchase Approvals.') % user.name)
        for reviewer in reviewers.filtered(lambda u: not u.share):
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=reviewer.id,
                                         summary='Portal RFQ review: %s' % self.name)

    def action_absar_portal_approve(self):
        user = self._portal_approver()
        for po in self:
            po._portal_lock()
            po._portal_check_company(user)
            if (not po.absar_portal_preparer_id or po.absar_portal_preparer_id == user or
                    po.absar_portal_review_state != 'submitted' or po.state not in ('draft', 'sent')):
                raise UserError(_('Only another preparer’s submitted RFQ can be approved.'))
            po.sudo().write({'absar_portal_review_state': 'approved',
                             'absar_portal_approver_id': user.id,
                             'absar_portal_approved_on': fields.Datetime.now()})
            po._portal_close_activities()
            po._portal_notify(po.absar_portal_preparer_id, _('RFQ %s approved') % po.name,
                              _('Approved by %s.') % user.name)
        return True

    def action_absar_portal_approve_confirm(self):
        self.ensure_one()
        user = self._portal_approver()
        self._portal_lock()
        self._portal_check_company(user)
        if (not self.absar_portal_preparer_id or self.absar_portal_preparer_id == user or
                self.absar_portal_review_state != 'submitted' or self.state not in ('draft', 'sent')):
            raise UserError(_('Only another employee’s submitted RFQ can be approved and confirmed.'))
        self.action_absar_portal_approve()
        # Invoke the complete native/installed confirmation chain. Submission
        # itself never invokes this method, creates receipts, or confirms a PO.
        return self.sudo().with_company(self.company_id).with_context(validate_analytic=True).button_confirm()

    def action_absar_portal_return(self):
        user = self._portal_approver()
        for po in self:
            po._portal_lock()
            po._portal_check_company(user)
            if (not po.absar_portal_preparer_id or po.absar_portal_preparer_id == user or
                    po.absar_portal_review_state not in ('submitted', 'approved') or
                    po.state not in ('draft', 'sent')):
                raise UserError(_('Only another preparer’s unconfirmed submitted or approved RFQ can be returned.'))
            if not (po.absar_portal_review_note or '').strip():
                raise ValidationError(_('Please explain the correction required.'))
            po.sudo().write({'absar_portal_review_state': 'returned',
                             'absar_portal_approver_id': False, 'absar_portal_approved_on': False})
            po._portal_close_activities()
            po._portal_notify(po.absar_portal_preparer_id, _('RFQ %s returned') % po.name,
                              po.absar_portal_review_note)
        return True

    def action_absar_portal_confirm(self):
        user = self._portal_approver()
        self.ensure_one()
        self._portal_lock()
        self._portal_check_company(user)
        if (not self.absar_portal_preparer_id or self.absar_portal_review_state != 'approved' or
                not self.absar_portal_approver_id or
                self.absar_portal_approver_id == self.absar_portal_preparer_id or
                self.state not in ('draft', 'sent')):
            raise UserError(_('Independent purchase approval is required before confirmation.'))
        # Never write native state directly or auto-approve native to-approve.
        # Keep caller identity so hard-coded checks in installed signing hooks apply.
        return self.sudo().with_company(self.company_id).with_context(validate_analytic=True).button_confirm()

    def action_absar_portal_submit(self):
        """Native Purchase entry point; the portal uses its scoped controller."""
        user = self._portal_actor('preparer')
        if user.share:
            raise AccessError(_('Submit this request through the purchase portal.'))
        self.check_access('write')
        for po in self.sorted('id'):
            po._portal_lock()
            po._portal_check_company(user)
            if po.state not in ('draft', 'sent'):
                raise UserError(_('Only an RFQ can be submitted for approval.'))
            if not po.absar_portal_preparer_id:
                # An internal issuer adopts only their own native RFQ. Never
                # claim another buyer's draft or change existing review history.
                if ((po.user_id and po.user_id != user) or
                        (not po.user_id and po.create_uid != user)):
                    raise UserError(_('Only the assigned buyer can submit this RFQ.'))
                po.write({'absar_portal_preparer_id': user.id, 'user_id': user.id})
            po._portal_submit()
        return True

    def button_confirm(self):
        rfqs = self.filtered(lambda po: po.state in ('draft', 'sent'))
        pending = rfqs.filtered(lambda po: not po.absar_portal_preparer_id or
                                po.absar_portal_review_state != 'approved')
        if pending:
            if pending != rfqs or len(rfqs) != len(self):
                raise UserError(_('Submit pending RFQs separately from approved orders.'))
            # Also guard the original method used by RPC and existing actions:
            # changing a button label alone must never allow direct confirmation.
            return pending.action_absar_portal_submit()
        for po in rfqs:
            user = po._portal_approver()
            po._portal_lock()
            po._portal_check_company(user)
            if (not po.absar_portal_approver_id or
                    po.absar_portal_preparer_id == user or
                    po.absar_portal_approver_id == po.absar_portal_preparer_id):
                raise UserError(_('This RFQ must be independently approved before confirmation.'))
        return super().button_confirm()

    def button_approve(self, force=False):
        for po in self:
            if po.state not in ('draft', 'sent', 'to approve'):
                continue
            user = po._portal_approver()
            po._portal_lock()
            po._portal_check_company(user)
            if (not po.absar_portal_preparer_id or po.absar_portal_review_state != 'approved' or
                    not po.absar_portal_approver_id or po.absar_portal_preparer_id == user or
                    po.absar_portal_approver_id == po.absar_portal_preparer_id):
                raise UserError(_('Independent purchase review approval is required first.'))
        return super().button_approve(force=force)

    def _portal_invalidate_review(self):
        for po in self.sorted('id'):
            if po.absar_portal_preparer_id and po.state in ('draft', 'sent', 'to approve'):
                po._portal_lock()
                if po.absar_portal_review_state in ('approved', 'submitted'):
                    po.sudo().write({
                        'absar_portal_review_state': 'returned',
                        'absar_portal_approver_id': False,
                        'absar_portal_approved_on': False,
                        'absar_portal_review_note': _('RFQ contents changed. Please check and resubmit for approval.'),
                    })
                    po._portal_close_activities()

    def write(self, vals):
        content_fields = {'partner_id', 'partner_ref', 'project_id', 'material_request_id',
                          'currency_id', 'company_id', 'date_order', 'date_planned', 'notes',
                          'payment_term_id', 'fiscal_position_id', 'incoterm_id',
                          'incoterm_location', 'picking_type_id', 'order_line', 'origin'}
        if content_fields.intersection(vals):
            self._portal_invalidate_review()
        return super().write(vals)

    def button_draft(self):
        result = super().button_draft()
        self.filtered('absar_portal_preparer_id').sudo().write({
            'absar_portal_review_state': 'draft', 'absar_portal_approver_id': False,
            'absar_portal_approved_on': False, 'absar_portal_review_note': False})
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    absar_expense_account_id = fields.Many2one('account.account', string='Portal Expense Account', check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env['purchase.order'].browse(list({v['order_id'] for v in vals_list if v.get('order_id')}))
        orders._portal_invalidate_review()
        return super().create(vals_list)

    def write(self, vals):
        content_fields = {'product_id', 'name', 'product_qty', 'product_uom', 'price_unit',
                          'discount', 'taxes_id', 'analytic_distribution', 'date_planned',
                          'absar_expense_account_id', 'display_type', 'sequence', 'order_id'}
        if content_fields.intersection(vals):
            self.order_id._portal_invalidate_review()
        return super().write(vals)

    def unlink(self):
        self.order_id._portal_invalidate_review()
        return super().unlink()

    def _prepare_account_move_line(self, move=False):
        vals = super()._prepare_account_move_line(move=move)
        if self.absar_expense_account_id:
            account = self.absar_expense_account_id
            if account.deprecated or self.company_id not in account.company_ids:
                raise ValidationError(_('The selected expense account is unavailable for this company.'))
            fiscal_position = move.fiscal_position_id if move else self.order_id.fiscal_position_id
            vals['account_id'] = (fiscal_position.map_account(account) if fiscal_position else account).id
        return vals
