# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class VendorInvoice(models.Model):
    _name = 'portal.vendor.invoice'
    _description = 'Vendor Portal Invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

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

    # ---------------------------------------------------------
    # 👇 NEW FIELD — Needed to show/hide Download button
    # ---------------------------------------------------------
    has_attachment = fields.Boolean(compute="_compute_has_attachment", store=False)

    def _compute_has_attachment(self):
        for rec in self:
            rec.has_attachment = bool(rec.attachment_id)
    # ---------------------------------------------------------

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

    portal_user_id = fields.Many2one(
        'res.users',
        string='Portal User',
        help='The vendor portal user who submitted this invoice.',
    )

    vendor_invoice_number = fields.Char(string="Vendor Invoice Number")

    # ---------------------------------------------------------
    # 👇 NEW METHOD — Backend-safe file download
    # ---------------------------------------------------------
    def action_download_attachment(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(_("No attachment found to download."))

        return {
            'type': 'ir.actions.act_url',
            'target': 'self',
            'url': f'/web/content/{self.attachment_id.id}?download=1',
        }
    # ---------------------------------------------------------

    # Sequence generation
    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('portal.vendor.invoice') or '/'
        return super(VendorInvoice, self).create(vals)
