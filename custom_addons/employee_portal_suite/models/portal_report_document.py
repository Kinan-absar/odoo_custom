# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PortalReportDocument(models.Model):
    _name = 'portal.report.document'
    _description = 'Portal Report Document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Report Title', required=True, tracking=True)
    description = fields.Text(string='Description')
    date = fields.Date(string='Report Date', default=fields.Date.context_today, required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    file = fields.Binary(string='PDF File', required=True, attachment=True)
    filename = fields.Char(string='Filename')
    mimetype = fields.Char(string='Mimetype', compute='_compute_mimetype', store=True)

    allowed_group_ids = fields.Many2many(
        'res.groups',
        'portal_report_document_group_rel',
        'document_id',
        'group_id',
        string='Visible to Portal Groups',
        required=True,
        help='Portal users must belong to at least one of these groups to see this report.',
    )

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    uploaded_by_id = fields.Many2one('res.users', string='Uploaded By', default=lambda self: self.env.user, readonly=True)

    @api.depends('filename')
    def _compute_mimetype(self):
        for rec in self:
            rec.mimetype = 'application/pdf' if (rec.filename or '').lower().endswith('.pdf') else False

    @api.constrains('filename')
    def _check_pdf_filename(self):
        for rec in self:
            if rec.filename and not rec.filename.lower().endswith('.pdf'):
                raise ValidationError(_('Only PDF files are allowed.'))

    def _portal_user_can_access(self, user):
        self.ensure_one()
        if not self.active:
            return False
        return bool(self.allowed_group_ids & user.groups_id)
