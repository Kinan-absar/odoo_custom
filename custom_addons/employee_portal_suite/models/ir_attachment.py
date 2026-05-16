# -*- coding: utf-8 -*-

from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    mr_attachment_category = fields.Selection([
        ("general", "General"),
        ("quotation", "Quotation"),
        ("invoice_submission", "Invoice Submission"),
    ], string="MR Attachment Category", default="general", copy=False)
