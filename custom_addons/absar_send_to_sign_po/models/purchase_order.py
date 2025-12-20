from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    sign_template_id = fields.Many2one("sign.template")
    signature_state = fields.Selection([
        ("draft", "Not Sent"),
        ("director_pending", "Pending Director Signature"),
        ("ceo_pending", "Pending CEO Signature"),
        ("signed", "Fully Signed"),
        ("rejected", "Rejected"),
    ], default="draft", tracking=True)

    revision = fields.Integer(default=0, tracking=True)

    # ---------------------------------------------------------------------
    # WRITE OVERRIDE – Reset signature workflow when PO is modified
    # ---------------------------------------------------------------------
    def write(self, vals):
        # Capture original state and revision BEFORE changes
        for po in self:
            po_state_before = po.signature_state
            po_revision_before = po.revision
    
        res = super().write(vals)
    
        for po in self:
            modifications = set(vals.keys())
    
            # Fields that justify revision increment
            meaningful_fields = {
                'order_line',
                'amount_total',
                'date_planned',
                'date_approve',
                'partner_id',
                'currency_id',
                'notes',
            }
    
            # If PO was fully signed BEFORE the change
            if po_state_before == "signed":
                # Do NOT increase revision on first signature
                if po_revision_before == 0:
                    # First time signed → revision stays 0
                    continue
    
                # If user edited meaningful data → revision++
                if modifications & meaningful_fields:
                    po.revision += 1
                    po.signature_state = "draft"
    
            # PO was NOT signed before, but user is editing a sent-for-sign PO
            elif po_state_before in ("director_pending", "ceo_pending"):
                if modifications & meaningful_fields:
                    po.revision += 1
                    po.signature_state = "draft"
    
        return res


    # ---------------------------------------------------------------------
    # SEND TO SIGN
    # ---------------------------------------------------------------------
    def action_send_to_sign(self):
        self.ensure_one()

        # Generate PDF report
        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            'purchase.report_purchaseorder',
            self.ids,
        )
        pdf_b64 = base64.b64encode(pdf_content)

        # Filename includes revision if exists
        filename = f"{self.name}"
        if self.revision > 0:
            filename += f"_R{self.revision}"
        filename += ".pdf"

        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': pdf_b64,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })

        # Create Sign Template
        template = self.env['sign.template'].create({
            'name': f"PO {self.name}",
            'attachment_id': attachment.id,
        })

        self.sign_template_id = template.id
        self.signature_state = "director_pending"
        self.message_post(body="PO sent for Director Signature.")

        # Final correct Sign URL
        return {
            "type": "ir.actions.act_url",
            "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}&name=Template%20"PO%20{self.name}"',
            "target": "self",
        }

    # ---------------------------------------------------------------------
    # CRON SYNC STATUS (Director → CEO → Completed → Rejected)
    # ---------------------------------------------------------------------
    @api.model
    def _cron_sync_sign_status(self):

        pos = self.search([
            ('sign_template_id', '!=', False)
        ])

        for po in pos:
            template = po.sign_template_id

            request = self.env['sign.request'].search(
                [('template_id', '=', template.id)],
                order="id desc",
                limit=1
            )
            if not request:
                continue

            # Director signed → Move to CEO
            if po.signature_state == 'director_pending' and request.nb_closed == 1:
                po.signature_state = 'ceo_pending'
                po.message_post(body="Director has signed. Waiting for CEO signature.")

            # CEO Signed → Completed
            if request.state == 'completed':
                po.signature_state = 'signed'
                po.message_post(body="PO fully signed.")

            # Rejected / Cancelled
            if request.state == 'canceled':
                po.signature_state = 'rejected'
                po.message_post(body="Signature request was rejected.")
