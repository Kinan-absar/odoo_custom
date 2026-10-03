from odoo import api, fields, models, _
from odoo.exceptions import UserError


SIGNATURE_STATES = [
    ("draft", "Not Sent"),
    ("pending", "Signing in Progress"),
    ("director_pending", "Legacy: Pending Director Signature"),
    ("ceo_pending", "Legacy: Pending CEO Signature"),
    ("signed", "Fully Signed"),
    ("rejected", "Rejected"),
]
ACTIVE_SIGNATURE_STATES = {"pending", "director_pending", "ceo_pending", "signed", "rejected"}


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    sign_request_id = fields.Many2one("sign.request", copy=False, readonly=True)
    signing_workflow_id = fields.Many2one("absar.sign.workflow", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    signature_status_text = fields.Char(default="Not Sent", copy=False, readonly=True)
    signature_completed_count = fields.Integer(default=0, copy=False, readonly=True)
    signature_total_count = fields.Integer(default=0, copy=False, readonly=True)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    project_id = fields.Many2one("project.project", string="Project", tracking=True, groups=False)

    def _reset_signing(self, reason):
        for po in self:
            if po.signature_state not in ACTIVE_SIGNATURE_STATES:
                continue
            revision = (po.revision or 0) + 1
            po.with_context(skip_po_sign_reset=True).write({
                "revision": revision,
                "signature_state": "draft",
                "signature_status_text": _("Not Sent"),
                "signature_completed_count": 0,
                "signature_total_count": 0,
                "sign_template_id": False,
                "sign_request_id": False,
                "signing_workflow_id": False,
            })
            po.message_post(body=_("%s Reset to Not Sent (Revision R%s).") % (reason, revision))

    def write(self, vals):
        previous = {po.id: po.signature_state for po in self}
        res = super().write(vals)
        if self.env.context.get("skip_po_sign_reset"):
            return res
        meaningful = {"amount_total", "date_planned", "date_approve", "partner_id", "currency_id", "notes", "project_id"}
        if meaningful.intersection(vals):
            for po in self:
                if previous.get(po.id) in ACTIVE_SIGNATURE_STATES:
                    po._reset_signing(_("PO modified after signing/sending."))
        return res

    def action_send_to_sign(self):
        self.ensure_one()
        if self.state != "purchase":
            raise UserError(_("Only a confirmed Purchase Order can be sent to Sign."))
        if self.signature_state != "draft":
            raise UserError(_("This Purchase Order has already been sent to Sign."))

        template, workflow, status = self.env["absar.sign.workflow.service"].create_template(
            self,
            "purchase.report_purchaseorder",
            _("Purchase Order"),
            [
                self.name,
                self.partner_id.name,
                self.material_request_id.name if hasattr(self, "material_request_id") and self.material_request_id else None,
                self.project_id.name if self.project_id else None,
            ],
        )
        self.with_context(skip_po_sign_reset=True).write({
            "sign_template_id": template.id,
            "signing_workflow_id": workflow.id,
            "signature_state": "pending",
            "signature_status_text": status,
            "signature_completed_count": 0,
            "signature_total_count": len(workflow.step_ids),
        })
        first = workflow.step_ids.sorted("sequence")[0]
        self.message_post(
            body=_("PO prepared for signing. Workflow: %(workflow)s. First signer: %(role)s (%(user)s).") % {
                "workflow": workflow.name,
                "role": first.name,
                "user": first.signer_user_id.name,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}&name=Template%20"PO%20{self.name}"',
            "target": "self",
        }

    def action_open_signature_status(self):
        self.ensure_one()
        return self.env["absar.sign.workflow.service"].open_status(self)

    @api.model
    def _cron_sync_sign_status(self):
        records = self.search([
            ("sign_template_id", "!=", False),
            ("signature_state", "in", ["pending", "director_pending", "ceo_pending"]),
        ])
        service = self.env["absar.sign.workflow.service"]
        for po in records:
            service.sync_record(po, "skip_po_sign_reset")


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def write(self, vals):
        states = {line.order_id.id: line.order_id.signature_state for line in self}
        res = super().write(vals)
        meaningful = {"product_qty", "price_unit", "product_id", "date_planned", "discount", "taxes_id", "product_uom"}
        if not self.env.context.get("skip_po_sign_reset") and meaningful.intersection(vals):
            for order in self.mapped("order_id"):
                if states.get(order.id) in ACTIVE_SIGNATURE_STATES:
                    order._reset_signing(_("PO line modified after signing/sending."))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_po_sign_reset"):
            for order in records.mapped("order_id"):
                if order.signature_state in ACTIVE_SIGNATURE_STATES:
                    order._reset_signing(_("PO line added after signing/sending."))
        return records

    def unlink(self):
        orders = {line.order_id.id: (line.order_id, line.order_id.signature_state) for line in self}
        res = super().unlink()
        if not self.env.context.get("skip_po_sign_reset"):
            for order, state in orders.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    order._reset_signing(_("PO line removed after signing/sending."))
        return res
