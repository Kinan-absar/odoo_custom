# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    """Extend partner to track first vendor portal login."""
    _inherit = 'res.partner'

    vendor_portal_onboarded = fields.Boolean(
        string='Vendor Portal Onboarding Done',
        default=False,
        help='True once the vendor has completed the first-login account details step.',
    )


class VendorInvoice(models.Model):
    _name = 'portal.vendor.invoice'
    _description = 'Vendor Portal Invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _sql_constraints = [
        ('unique_vendor_invoice_number',
         'UNIQUE(partner_id, vendor_invoice_number)',
         'This vendor invoice number already exists for this vendor.')
    ]

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default='/',
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        tracking=True,
        domain=[('supplier_rank', '>', 0)],
    )

    po_id = fields.Many2one(
        'purchase.order',
        string='Related Purchase Order',
        tracking=True,
    )

    invoice_date = fields.Date(
        string='Invoice Date',
        tracking=True,
    )

    amount_total = fields.Monetary(
        string='Total Amount',
        tracking=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id.id,
        tracking=True,
    )

    attachment_id = fields.Many2one(
        'ir.attachment',
        string='Invoice Document',
        help='Uploaded invoice file (PDF or image).',
    )

    has_attachment = fields.Boolean(compute="_compute_has_attachment", store=False)

    def _compute_has_attachment(self):
        for rec in self:
            rec.has_attachment = bool(rec.attachment_id)

    state = fields.Selection([
        ('submitted', 'Submitted'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ],
        string='Status',
        default='submitted',
        tracking=True,
    )

    notes = fields.Text(string='Vendor Notes')
    internal_notes = fields.Text(string='Internal Notes')

    review_comment = fields.Text(
        string='Review Comment for Vendor',
        tracking=True,
        help='This message will be visible to the vendor in their portal invoice detail view.',
    )

    portal_user_id = fields.Many2one(
        'res.users',
        string='Portal User',
        help='The vendor portal user who submitted this invoice.',
    )

    vendor_invoice_number = fields.Char(string="Vendor Invoice Number")

    # ------------------------------------------------------------------
    # State transition methods
    # ------------------------------------------------------------------

    def action_set_review(self):
        for rec in self:
            rec.write({'state': 'review'})
            rec.message_post(body=_("Invoice moved to <b>Under Review</b>."))

    def action_approve(self):
        for rec in self:
            rec.write({'state': 'approved'})
            rec.message_post(body=_("Invoice has been <b>Approved</b>."))

    def action_reject(self):
        for rec in self:
            rec.write({'state': 'rejected'})
            rec.message_post(body=_("Invoice has been <b>Rejected</b>."))

    def action_reset_submitted(self):
        for rec in self:
            rec.write({'state': 'submitted'})
            rec.message_post(body=_("Invoice has been reset to <b>Submitted</b>."))

    def action_download_attachment(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("No attachment found to download."))
        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': f'/web/content/{self.attachment_id.id}?download=1',
        }

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('portal.vendor.invoice') or '/'

        record = super().create(vals)

        if record.attachment_id:
            record.attachment_id.write({
                'res_model': record._name,
                'res_id': record.id,
            })

        group = self.env.ref(
            'customer_vendor_portal.group_vendor_invoice_reviewer',
            raise_if_not_found=False
        )
        if group:
            for user in group.users.filtered(lambda u: u.active):
                record.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_("New Vendor Invoice Submitted"),
                    note=_("A new vendor invoice has been uploaded and requires review."),
                )

        return record
