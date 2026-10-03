import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError


SIGNATURE_STATES = [
    ("draft", "Not Sent"),
    ("director_pending", "Pending Director Signature"),
    ("ceo_pending", "Pending CEO Signature"),
    ("signed", "Fully Signed"),
    ("rejected", "Rejected"),
]

ACTIVE_SIGNATURE_STATES = {"director_pending", "ceo_pending", "signed", "rejected"}


def _reset_signature(record, reason):
    """Reset one signed/sent construction document and increment its revision."""
    if record.signature_state not in ACTIVE_SIGNATURE_STATES:
        return
    new_revision = (record.revision or 0) + 1
    record.with_context(skip_construction_sign_reset=True).write({
        "revision": new_revision,
        "signature_state": "draft",
        "sign_template_id": False,
    })
    record.message_post(
        body=_("%s Reset to Not Sent (Revision R%s).") % (reason, new_revision)
    )


def _create_sign_template(record, report_xmlid, document_label, filename_parts):
    record.ensure_one()

    if record.signature_state != "draft":
        raise UserError(_("This document has already been sent to Sign. Modify the document first if a new revision is required."))

    pdf_content, pdf_format = record.env["ir.actions.report"]._render_qweb_pdf(
        report_xmlid,
        record.ids,
    )

    clean_parts = [str(p).strip() for p in filename_parts if p and str(p).strip()]
    filename = " - ".join(clean_parts) or record.display_name
    if record.revision:
        filename += f"_R{record.revision}"
    filename += ".pdf"

    attachment = record.env["ir.attachment"].create({
        "name": filename,
        "datas": base64.b64encode(pdf_content),
        "type": "binary",
        "mimetype": "application/pdf",
        "res_model": record._name,
        "res_id": record.id,
    })

    template = record.env["sign.template"].create({
        "name": f"{document_label} - {filename[:-4]}",
        "attachment_id": attachment.id,
    })

    record.with_context(skip_construction_sign_reset=True).write({
        "sign_template_id": template.id,
        "signature_state": "director_pending",
    })
    record.message_post(body=_("%s sent for Director Signature.") % document_label)

    return {
        "type": "ir.actions.act_url",
        "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}&name=Template%20"{document_label}%20{record.display_name}"',
        "target": "self",
    }


def _open_sign_template(record):
    record.ensure_one()
    if not record.sign_template_id:
        raise UserError(_("No Sign template is linked to this document."))
    template = record.sign_template_id
    return {
        "type": "ir.actions.act_url",
        "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}',
        "target": "self",
    }


class ConstructionContract(models.Model):
    _inherit = "construction.contract"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_send_to_sign(self):
        self.ensure_one()
        if self.state not in ("approved", "active", "completed", "closed"):
            raise UserError(_("Only an approved or active/completed construction contract can be sent to Sign."))
        return _create_sign_template(
            self,
            "construction_contract_management.action_report_construction_contract",
            _("Contract"),
            [self.name, self.partner_id.name, self.project_id.name if self.project_id else None],
        )

    def action_open_sign_template(self):
        return _open_sign_template(self)

    def action_open_signature_status(self):
        self.ensure_one()
        if self.sign_template_id:
            return _open_sign_template(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signature"),
                "message": _("This document has not been sent to Sign yet."),
                "type": "info",
                "sticky": False,
            },
        }

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {
            "project_id", "partner_id", "contract_direction", "customer_reference",
            "scope", "date_start", "date_end", "original_amount", "payment_term_id",
            "retention_percent", "advance_percent", "vat_percent", "notes",
        }
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("Contract modified after signing/sending."))
        return res

    @api.model
    def _cron_sync_construction_sign_status(self):
        for model_name in ("construction.contract", "construction.measurement", "construction.ipc"):
            records = self.env[model_name].search([
                ("sign_template_id", "!=", False),
                ("signature_state", "in", ["director_pending", "ceo_pending"]),
            ])
            for rec in records:
                request = self.env["sign.request"].search(
                    [("template_id", "=", rec.sign_template_id.id)],
                    order="id desc",
                    limit=1,
                )
                if not request:
                    continue
                if request.state in ("canceled", "refused"):
                    rec.with_context(skip_construction_sign_reset=True).signature_state = "rejected"
                    rec.message_post(body=_("Signature request was rejected or cancelled."))
                    continue
                if request.state == "signed":
                    rec.with_context(skip_construction_sign_reset=True).signature_state = "signed"
                    rec.message_post(body=_("Document fully signed."))
                    continue
                signed_items = self.env["sign.request.item"].search_count([
                    ("sign_request_id", "=", request.id),
                    ("state", "=", "completed"),
                ])
                if rec.signature_state == "director_pending" and signed_items >= 1:
                    rec.with_context(skip_construction_sign_reset=True).signature_state = "ceo_pending"
                    rec.message_post(body=_("Director has signed. Waiting for CEO signature."))


class ConstructionMeasurement(models.Model):
    _inherit = "construction.measurement"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_send_to_sign(self):
        self.ensure_one()
        if self.state != "approved":
            raise UserError(_("Only an approved measurement can be sent to Sign."))
        return _create_sign_template(
            self,
            "construction_contract_management.action_report_construction_measurement",
            _("Measurement"),
            [
                self.name,
                self.contract_id.name,
                self.contract_id.partner_id.name,
                self.project_id.name if self.project_id else None,
            ],
        )

    def action_open_sign_template(self):
        return _open_sign_template(self)

    def action_open_signature_status(self):
        self.ensure_one()
        if self.sign_template_id:
            return _open_sign_template(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signature"),
                "message": _("This document has not been sent to Sign yet."),
                "type": "info",
                "sticky": False,
            },
        }

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {
            "contract_id", "contract_order_id", "date", "period_from", "period_to",
            "prepared_by", "checked_by",
        }
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("Measurement modified after signing/sending."))
        return res


class ConstructionIPC(models.Model):
    _inherit = "construction.ipc"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_send_to_sign(self):
        self.ensure_one()
        if self.state not in ("approved", "done"):
            raise UserError(_("Only an approved or done IPC can be sent to Sign."))
        return _create_sign_template(
            self,
            "construction_contract_management.action_report_construction_ipc",
            _("IPC"),
            [
                self.name,
                self.contract_id.name,
                self.contract_id.partner_id.name,
                self.project_id.name if self.project_id else None,
            ],
        )

    def action_open_sign_template(self):
        return _open_sign_template(self)

    def action_open_signature_status(self):
        self.ensure_one()
        if self.sign_template_id:
            return _open_sign_template(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signature"),
                "message": _("This document has not been sent to Sign yet."),
                "type": "info",
                "sticky": False,
            },
        }

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {
            "contract_id", "contract_order_id", "measurement_id", "ipc_date",
            "period_from", "period_to", "deduct_advance", "deduct_retention_on_invoice",
            "deduction_amount",
        }
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("IPC modified after signing/sending."))
        return res


class ConstructionContractBOQLine(models.Model):
    _inherit = "construction.contract.boq.line"

    def _reset_parent_contract_signatures(self, states=None, reason=None):
        contracts = self.mapped("contract_id")
        for contract in contracts:
            expected = states.get(contract.id) if states else contract.signature_state
            if expected in ACTIVE_SIGNATURE_STATES:
                _reset_signature(contract, reason or _("Contract BOQ changed after signing/sending."))

    def write(self, vals):
        states = {line.contract_id.id: line.contract_id.signature_state for line in self if line.contract_id}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {"sequence", "display_type", "item_code", "description", "uom_id", "contract_qty", "unit_rate"}
        if meaningful.intersection(vals):
            self._reset_parent_contract_signatures(states, _("Contract BOQ modified after signing/sending."))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_construction_sign_reset"):
            records._reset_parent_contract_signatures(reason=_("Contract BOQ line added after signing/sending."))
        return records

    def unlink(self):
        contracts = {line.contract_id.id: (line.contract_id, line.contract_id.signature_state) for line in self if line.contract_id}
        res = super().unlink()
        if not self.env.context.get("skip_construction_sign_reset"):
            for contract, state in contracts.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(contract, _("Contract BOQ line removed after signing/sending."))
        return res


class ConstructionMeasurementLine(models.Model):
    _inherit = "construction.measurement.line"

    def write(self, vals):
        parents = {line.measurement_id.id: (line.measurement_id, line.measurement_id.signature_state) for line in self if line.measurement_id}
        res = super().write(vals)
        if not self.env.context.get("skip_construction_sign_reset") and {"boq_line_id", "previous_qty", "current_qty", "remarks"}.intersection(vals):
            for parent, state in parents.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("Measurement lines modified after signing/sending."))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_construction_sign_reset"):
            for parent in records.mapped("measurement_id"):
                if parent.signature_state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("Measurement line added after signing/sending."))
        return records

    def unlink(self):
        parents = {line.measurement_id.id: (line.measurement_id, line.measurement_id.signature_state) for line in self if line.measurement_id}
        res = super().unlink()
        if not self.env.context.get("skip_construction_sign_reset"):
            for parent, state in parents.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("Measurement line removed after signing/sending."))
        return res


class ConstructionIPCLine(models.Model):
    _inherit = "construction.ipc.line"

    def write(self, vals):
        parents = {line.ipc_id.id: (line.ipc_id, line.ipc_id.signature_state) for line in self if line.ipc_id}
        res = super().write(vals)
        if not self.env.context.get("skip_construction_sign_reset") and {"boq_line_id", "measurement_line_id", "previous_qty", "current_qty", "cumulative_qty", "unit_rate"}.intersection(vals):
            for parent, state in parents.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("IPC lines modified after signing/sending."))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_construction_sign_reset"):
            for parent in records.mapped("ipc_id"):
                if parent.signature_state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("IPC line added after signing/sending."))
        return records

    def unlink(self):
        parents = {line.ipc_id.id: (line.ipc_id, line.ipc_id.signature_state) for line in self if line.ipc_id}
        res = super().unlink()
        if not self.env.context.get("skip_construction_sign_reset"):
            for parent, state in parents.values():
                if state in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(parent, _("IPC line removed after signing/sending."))
        return res
