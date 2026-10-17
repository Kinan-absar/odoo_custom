from odoo import api, fields, models, _

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    absar_portal_creator_id = fields.Many2one('res.users', string='Portal Prepared By', readonly=True, index=True, copy=False)
    absar_portal_review_state = fields.Selection([
        ('draft', 'Portal Draft'), ('submitted', 'Awaiting Internal Approval'),
        ('approved', 'Approved for Sending'), ('returned', 'Returned for Correction')],
        string='Portal Review', default='draft', copy=False, tracking=True, index=True)
    absar_portal_review_note = fields.Text(string='Review Notes', copy=False)
    absar_portal_approver_id = fields.Many2one('res.users', string='Portal Approved By', readonly=True, copy=False)

    @api.model
    def _absar_portal_sync_salesperson(self):
        orders = self.sudo().search([('absar_portal_creator_id', '!=', False),
                                     ('state', 'in', ('draft', 'sent'))])
        for order in orders:
            if order.user_id != order.absar_portal_creator_id:
                order.sudo().write({'user_id': order.absar_portal_creator_id.id})
        return True

    def _absar_portal_notify_reviewers(self):
        self.ensure_one()
        group = self.env.ref('absar_portal_sales.group_portal_sales_approver', raise_if_not_found=False)
        if not group:
            return
        users = group.sudo().users.filtered(lambda u: u.active and u.id != self.absar_portal_creator_id.id and self.company_id in u.company_ids)
        internal_users=users.filtered(lambda u: not u.share and u.has_group('sales_team.group_sale_salesman'))
        if internal_users:
            self.sudo().activity_schedule('mail.mail_activity_data_todo', user_id=internal_users[0].id,
                summary=_('Portal quotation pending approval: %s') % self.name,
                note=_('Review the quotation in Sales or Employee Portal. Approve for sending or return for correction; do not confirm the Sales Order.'))
        # Replace earlier submission alerts when a returned offer is resubmitted.
        self.env['absar.portal.sales.bell.event'].sudo().search([
            ('order_id', '=', self.id), ('category', '=', 'sales_approval')
        ]).unlink()
        for user in users:
            self.env['absar.portal.sales.bell.event'].sudo().create({
                'recipient_id': user.id, 'order_id': self.id,
                'category': 'sales_approval', 'event_type': 'submitted',
            })
            if user.partner_id:
                self.sudo().message_post(body=_('Quotation %s is awaiting your internal review. Portal: /my/employee/sales/%s') % (self.name,self.id), partner_ids=[user.partner_id.id], message_type='notification', subtype_xmlid='mail.mt_comment')

    def _absar_portal_notify_creator(self, message, event_type=None):
        self.ensure_one()
        user=self.absar_portal_creator_id
        if user and event_type in ('approved', 'returned'):
            self.env['absar.portal.sales.bell.event'].sudo().create({
                'recipient_id': user.id, 'order_id': self.id,
                'category': 'sales_decision', 'event_type': event_type,
                'note': message[:255],
            })
        if user and user.partner_id:
            self.sudo().message_post(body=message, partner_ids=[user.partner_id.id],message_type='notification',subtype_xmlid='mail.mt_comment')

    def action_absar_portal_approve(self):
        if not self.env.user.has_group('absar_portal_sales.group_portal_sales_approver'):
            from odoo.exceptions import AccessError
            raise AccessError(_('Only portal sales approvers can approve offers.'))
        for order in self:
            if order.absar_portal_review_state != 'submitted' or order.state != 'draft' or order.absar_portal_creator_id == self.env.user:
                from odoo.exceptions import UserError
                raise UserError(_('This quotation cannot be approved by this user.'))
            order.write({'absar_portal_review_state':'approved','absar_portal_approver_id':self.env.user.id})
            order._absar_portal_notify_creator(_('Your quotation %s has been approved for sending. You can now print it from Employee Portal.') % order.name, event_type='approved')
        return True

    def action_absar_portal_return(self):
        if not self.env.user.has_group('absar_portal_sales.group_portal_sales_approver'):
            from odoo.exceptions import AccessError
            raise AccessError(_('Only portal sales approvers can return offers.'))
        for order in self:
            if order.absar_portal_review_state != 'submitted' or order.state != 'draft' or order.absar_portal_creator_id == self.env.user:
                from odoo.exceptions import UserError
                raise UserError(_('This quotation cannot be returned by this user.'))
            note = order.absar_portal_review_note or _('Please revise this offer and resubmit.')
            order.write({'absar_portal_review_state':'returned','absar_portal_review_note':note})
            order._absar_portal_notify_creator(_('Your quotation %s was returned for correction: %s') % (order.name,note), event_type='returned')
        return True
