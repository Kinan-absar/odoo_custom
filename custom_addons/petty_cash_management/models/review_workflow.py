"""Sequential petty cash review. Public actions validate the real caller first."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

_TOKEN = object()
GROUP = 'petty_cash_management.'
STAGES = {'submitted': ('group_petty_cash_reviewer_1', 'Accounting Review'),
          'review_2': ('group_petty_cash_reviewer_2', 'Supervisor Review'),
          'manager_approval': ('group_petty_cash_manager', 'Manager Approval')}
PROTECTED = {'state','review_1_by','review_1_date','review_2_by','review_2_date',
             'manager_approved_by','manager_approved_date','returned_by','returned_date','correction_reason','journal_entry_id'}

class PettyCashReview(models.Model):
    _inherit = 'petty.cash'

    state = fields.Selection(selection_add=[('submitted','Accounting Review'),('review_2','Supervisor Review'),
        ('manager_approval','Manager Approval'),('approved',)],
        ondelete={'review_2':'set default','manager_approval':'set default'}, copy=False)
    journal_entry_id = fields.Many2one(copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                readonly=True, index=True)

    @api.constrains('company_id', 'journal_id')
    def _check_report_journal_company(self):
        for rec in self:
            if rec.journal_id and rec.journal_id.company_id != rec.company_id:
                raise UserError(_('The journal must belong to the petty cash report company.'))
    review_1_by = fields.Many2one('res.users', string='Accounting Reviewer', readonly=True, copy=False, tracking=True)
    review_1_date = fields.Datetime(string='Accounting Review Date', readonly=True, copy=False)
    review_2_by = fields.Many2one('res.users', string='Accounting Supervisor', readonly=True, copy=False, tracking=True)
    review_2_date = fields.Datetime(string='Supervisor Review Date', readonly=True, copy=False)
    manager_approved_by = fields.Many2one('res.users', string='Final Approver', readonly=True, copy=False, tracking=True)
    manager_approved_date = fields.Datetime(readonly=True, copy=False)
    correction_reason = fields.Text(readonly=True, copy=False, tracking=True)
    returned_by = fields.Many2one('res.users', readonly=True, copy=False)
    returned_date = fields.Datetime(readonly=True, copy=False)
    can_review_stage = fields.Boolean(compute='_compute_review_buttons')
    can_create_voucher = fields.Boolean(compute='_compute_review_buttons')
    can_open_voucher = fields.Boolean(compute='_compute_review_buttons')

    def _is_review_user(self, user=None):
        user = user or self.env.user
        return user.active and not user._is_public() and any(user.has_group(GROUP+name) for name in
                   ('group_petty_cash_reviewer_1','group_petty_cash_reviewer_2','group_petty_cash_manager'))

    def _review_company(self, user=None):
        self.ensure_one();user=user or self.env.user
        if not user.active or user._is_public() or not self.company_id or self.company_id not in user.company_ids:
            raise AccessError(_('This petty cash report is not available in your companies.'))

    def _can_review(self, user=None):
        self.ensure_one();user=user or self.env.user
        if not user.active or user._is_public() or self.company_id not in user.company_ids or self.state not in STAGES:
            return False
        return user.has_group(GROUP+STAGES[self.state][0])

    @api.depends_context('uid')
    @api.depends('state','journal_entry_id','review_1_by','review_2_by','company_id')
    def _compute_review_buttons(self):
        for rec in self:
            allowed=rec._is_review_user() and rec.company_id in self.env.user.company_ids
            rec.can_review_stage=rec._can_review()
            rec.can_create_voucher=allowed and rec.state=='approved' and not rec.journal_entry_id
            rec.can_open_voucher=allowed and bool(rec.journal_entry_id)

    def _review_lock(self):
        self.ensure_one()
        self.flush_recordset(['state','journal_entry_id'])
        self.env.cr.execute('SELECT id FROM petty_cash WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _flow_write(self, values):
        return self.sudo().with_context(_petty_review_token=_TOKEN).write(values)

    def write(self, values):
        if PROTECTED.intersection(values) and self.env.context.get('_petty_review_token') is not _TOKEN:
            raise AccessError(_('Use the petty cash workflow buttons to change approval or voucher information.'))
        for rec in self:
            if rec.state!='draft' and set(values).intersection({'company_id','user_id','date','currency_id','journal_id','petty_cash_account_id','input_vat_account_id','line_ids'}):
                raise UserError(_('Return the report for correction before changing its expenses or accounting setup.'))
        return super().write(values)

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            if values.get('journal_id') and not values.get('company_id'):
                journal = self.env['account.journal'].browse(values['journal_id'])
                values['company_id'] = journal.company_id.id
            if values.get('state','draft')!='draft' or (PROTECTED-{'state'}).intersection(values):
                raise AccessError(_('New petty cash reports must start in Draft.'))
        return super().create(values_list)

    def _review_notify(self, users, title, targeted=False):
        """Native inbox notification plus an activity for internal reviewers."""
        self.ensure_one()
        users=users.filtered(lambda u:u.active and self.company_id in u.company_ids)
        if users:
            if targeted:
                self.sudo().message_notify(body=title, subject=title, partner_ids=users.partner_id.ids)
            else:
                self.sudo().message_post(body=title,partner_ids=users.partner_id.ids,subtype_xmlid='mail.mt_comment')
            for user in users.filtered(lambda u:not u.share):
                self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=user.id, summary=title)

    def _notify_next_review(self):
        self.ensure_one()
        users=self.env.ref(GROUP+STAGES[self.state][0]).sudo().users
        users=users.filtered(lambda u:self._can_review(u))
        if not users:
            raise UserError(_('Assign an active, eligible %s user in this company before continuing.') % STAGES[self.state][1])
        self._review_notify(users, _('%s: %s required') % (self.name,STAGES[self.state][1]))

    def action_submit(self):
        user=self.env.user
        for rec in self:
            rec._review_company(user);rec._review_lock()
            if rec.user_id!=user or not (user.has_group(GROUP+'group_petty_cash_user') or user.has_group(GROUP+'group_portal_petty_cash_user')):
                raise AccessError(_('Only the submitting petty cash user can submit this report.'))
            if rec.state!='draft' or not rec.line_ids:raise UserError(_('Submit a draft report with expense lines.'))
            rec._flow_write({'state':'submitted','review_1_by':False,'review_1_date':False,'review_2_by':False,
                'review_2_date':False,'manager_approved_by':False,'manager_approved_date':False,'correction_reason':False,'returned_by':False,'returned_date':False})
            rec._notify_next_review()
        return True

    def action_approve(self):
        user=self.env.user
        for rec in self:
            rec._review_company(user);rec._review_lock()
            if not rec._can_review(user):raise AccessError(_('You are not assigned to the role required for this stage.'))
            old_state=rec.state
            actor_field,date_field,next_state={
                'submitted':('review_1_by','review_1_date','review_2'),
                'review_2':('review_2_by','review_2_date','manager_approval'),
                'manager_approval':('manager_approved_by','manager_approved_date','approved')}[old_state]
            rec._flow_write({actor_field:user.id,date_field:fields.Datetime.now(),'state':next_state})
            rec.sudo().activity_ids.filtered(lambda a:a.user_id==user).action_done()
            rec.sudo().message_post(body=_('%s completed by %s.') % (STAGES[old_state][1],user.name))
            if next_state=='approved':
                reviewers=self.env.ref(GROUP+'group_petty_cash_reviewer_1').sudo().users
                rec._review_notify(reviewers,_('%s approved. Ready to create the voucher.') % rec.name, targeted=True)
            else:rec._notify_next_review()
        return True

    def action_portal_approve(self):return self.action_approve()

    def _return_or_refuse(self, reason, refused=False):
        user=self.env.user
        if not str(reason or '').strip():raise UserError(_('Enter a correction or rejection reason.'))
        for rec in self:
            rec._review_company(user);rec._review_lock()
            if not rec._can_review(user):raise AccessError(_('Only the reviewer for the current stage can return or reject this report.'))
            rec._flow_write({'state':'refused' if refused else 'draft','correction_reason':str(reason).strip(),
                             'returned_by':user.id,'returned_date':fields.Datetime.now()})
            rec.sudo().activity_ids.action_done()
            rec._review_notify(rec.user_id,_('%s: %s — %s') % (rec.name,'Rejected' if refused else 'Returned for correction',reason))
        return True

    def action_return_for_correction(self):
        self.ensure_one()
        if not self._can_review():raise AccessError(_('You cannot review this stage.'))
        return {'type':'ir.actions.act_window','name':_('Return for Correction'),'res_model':'petty.cash.review.return',
                'view_mode':'form','target':'new','context':{'default_report_id':self.id}}

    def action_refuse(self):
        return self.action_return_for_correction()

    def action_portal_refuse(self, reason=None):return self._return_or_refuse(reason,refused=True)

    def action_reset_to_draft(self):
        for rec in self:
            rec._review_company();rec._review_lock()
            if not self._is_review_user() or rec.state not in ('refused','approved') or rec.journal_entry_id:
                raise AccessError(_('Only reviewers can reset a rejected/approved report without a voucher.'))
            rec._flow_write({'state':'draft'})
        return True

    def action_create_journal_entry(self):
        self.ensure_one();self._review_company();self._review_lock()
        if not self._is_review_user() or self.state!='approved':
            raise AccessError(_('All three reviews must be completed before a reviewer or manager creates the voucher.'))
        if self.journal_entry_id:return self.action_open_voucher()
        # Reuse the original draft journal entry/tax/attachment implementation.
        return super(PettyCashReview,self.sudo().with_company(self.company_id).with_context(_petty_review_token=_TOKEN)).action_create_journal_entry()

    def action_open_voucher(self):
        self.ensure_one();self._review_company()
        if not self._is_review_user() or not self.journal_entry_id:raise AccessError(_('Voucher is not available.'))
        return {'type':'ir.actions.act_window','res_model':'account.move','res_id':self.journal_entry_id.id,'view_mode':'form'}


class PettyCashReviewReturn(models.TransientModel):
    _name='petty.cash.review.return'
    _description='Return Petty Cash for Correction'
    report_id=fields.Many2one('petty.cash',required=True,readonly=True)
    reason=fields.Text(required=True)
    def action_return(self):
        self.ensure_one();self.report_id._return_or_refuse(self.reason)
        return {'type':'ir.actions.act_window_close'}


class PettyCashLineReviewLock(models.Model):
    _inherit='petty.cash.line'
    def _check_review_draft(self):
        if any(line.petty_cash_id.state!='draft' for line in self):
            raise UserError(_('Expense lines can only be changed in Draft.'))
    def write(self, values):
        self._check_review_draft()
        if values.get('petty_cash_id'):
            target=self.env['petty.cash'].browse(values['petty_cash_id'])
            if target.state!='draft':raise UserError(_('Expense lines can only be changed in Draft.'))
        return super().write(values)
    def unlink(self):
        self._check_review_draft();return super().unlink()
    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            report=self.env['petty.cash'].browse(values.get('petty_cash_id'))
            if report and report.state!='draft':raise UserError(_('Expense lines can only be changed in Draft.'))
        return super().create(values_list)
