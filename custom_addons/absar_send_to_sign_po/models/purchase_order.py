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

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True,
        groups=False
    )

    # ---------------------------------------------------------------------
    # WRITE OVERRIDE – Reset when PO header fields change
    # ---------------------------------------------------------------------
    def write(self, vals):
        po_states_before = {po.id: po.signature_state for po in self}

        res = super().write(vals)

        meaningful_fields = {
            'amount_total', 'date_planned', 'date_approve',
            'partner_id', 'currency_id', 'notes',
        }

        if set(vals.keys()) & meaningful_fields:
            for po in self:
                state_before = po_states_before[po.id]
                if state_before in ('director_pending', 'ceo_pending', 'signed'):
                    po.revision += 1
                    po.signature_state = 'draft'
                    po.message_post(body=f"PO modified after signing. Reset to draft (Revision {po.revision}).")

        return res

    # ---------------------------------------------------------------------
    # SEND TO SIGN
    # ---------------------------------------------------------------------
    def action_send_to_sign(self):
        self.ensure_one()

        pdf_content, _ = self.env['ir.actions.report']._render_qweb_pdf(
            'purchase.report_purchaseorder',
            self.ids,
        )
        pdf_b64 = base64.b64encode(pdf_content)

        filename_parts = [
            self.name,
            self.partner_id.name,
            self.material_request_id.name if hasattr(self, 'material_request_id') and self.material_request_id else None,
            self.project_id.name if self.project_id else None,
        ]

        filename = " - ".join(p for p in filename_parts if p)
        if self.revision > 0:
            filename += f"_R{self.revision}"
        filename += ".pdf"

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': pdf_b64,
            'type': 'binary',
            'mimetype': 'application/pdf',
        })

        template = self.env['sign.template'].create({
            'name': f"PO - {filename.replace('.pdf', '')}",
            'attachment_id': attachment.id,
        })

        self.sign_template_id = template.id
        self.signature_state = "director_pending"
        self.message_post(body="PO sent for Director Signature.")

        return {
            "type": "ir.actions.act_url",
            "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}&name=Template%20"PO%20{self.name}"',
            "target": "self",
        }

    # ---------------------------------------------------------------------
    # CRON SYNC STATUS
    # ---------------------------------------------------------------------
    @api.model
    def _cron_sync_sign_status(self):
        pos = self.search([
            ('sign_template_id', '!=', False),
            ('signature_state', 'in', ['director_pending', 'ceo_pending']),
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

            if request.state in ('canceled', 'refused'):
                po.signature_state = 'rejected'
                po.message_post(body="Signature request was rejected or cancelled.")
                continue

            if request.state == 'signed':
                po.signature_state = 'signed'
                po.message_post(body="PO fully signed.")
                continue

            signed_items = self.env['sign.request.item'].search_count([
                ('sign_request_id', '=', request.id),
                ('state', '=', 'completed'),
            ])

            if po.signature_state == 'director_pending' and signed_items >= 1:
                po.signature_state = 'ceo_pending'
                po.message_post(body="Director has signed. Waiting for CEO signature.")


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # ---------------------------------------------------------------------
    # LINE WRITE – Reset when line quantities/prices change
    # ---------------------------------------------------------------------
    def write(self, vals):
        po_states_before = {
            line.order_id.id: line.order_id.signature_state
            for line in self
        }

        res = super().write(vals)

        line_meaningful_fields = {
            'product_qty', 'price_unit', 'product_id',
            'date_planned', 'discount', 'taxes_id', 'product_uom',
        }

        if set(vals.keys()) & line_meaningful_fields:
            seen_orders = set()
            for line in self:
                order = line.order_id
                if order.id in seen_orders:
                    continue
                seen_orders.add(order.id)
                state_before = po_states_before.get(order.id)
                if state_before in ('director_pending', 'ceo_pending', 'signed'):
                    order.revision += 1
                    order.signature_state = 'draft'
                    order.message_post(body=f"PO line modified after signing. Reset to draft (Revision {order.revision}).")

        return res

    # ---------------------------------------------------------------------
    # LINE CREATE – Reset if a new line is added
    # ---------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        seen_orders = set()
        for line in records:
            order = line.order_id
            if order.id in seen_orders:
                continue
            seen_orders.add(order.id)
            if order.signature_state in ('director_pending', 'ceo_pending', 'signed'):
                order.revision += 1
                order.signature_state = 'draft'
                order.message_post(body=f"PO line added after signing. Reset to draft (Revision {order.revision}).")
        return records

    # ---------------------------------------------------------------------
    # LINE UNLINK – Reset if a line is deleted
    # ---------------------------------------------------------------------
    def unlink(self):
        order_states = {
            line.order_id.id: (line.order_id, line.order_id.signature_state)
            for line in self
        }
        res = super().unlink()
        seen = set()
        for order_id, (order, state_before) in order_states.items():
            if order_id in seen:
                continue
            seen.add(order_id)
            if state_before in ('director_pending', 'ceo_pending', 'signed'):
                order.revision += 1
                order.signature_state = 'draft'
                order.message_post(body=f"PO line removed after signing. Reset to draft (Revision {order.revision}).")
        return res
