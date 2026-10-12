import io

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader

from odoo.addons.absar_sign_workflow_core.tools.signature_anchors import resolve_signature_placements

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


def _reset_signature(record, reason):
    if record.signature_state not in ACTIVE_SIGNATURE_STATES:
        return
    new_revision = (record.revision or 0) + 1
    record.with_context(skip_construction_sign_reset=True).write({
        "revision": new_revision,
        "signature_state": "draft",
        "signature_status_text": _("Not Sent"),
        "signature_completed_count": 0,
        "signature_total_count": 0,
        "sign_template_id": False,
        "sign_request_id": False,
        "signing_workflow_id": False,
    })
    record.message_post(body=_("%s Reset to Not Sent (Revision R%s).") % (reason, new_revision))


def _create_sign_template(record, report_xmlid, document_label, filename_parts):
    record.ensure_one()
    if record.signature_state != "draft":
        raise UserError(_("This document has already been sent to Sign. Modify the document first if a new revision is required."))

    service = record.env["absar.sign.workflow.service"]
    workflow = service.get_workflow(record, required=True)
    pdf_content, _format = record.env["ir.actions.report"]._render_qweb_pdf(report_xmlid, record.ids)
    page_count = len(PdfReader(io.BytesIO(pdf_content)).pages)
    anchors, issues = resolve_signature_placements(
        pdf_content, page_count, workflow.step_ids, prefer_signature_area=True,
    )
    template, workflow, status = service.with_context(
        absar_sign_bottom=True, absar_sign_page=page_count, absar_sign_anchors=anchors,
    ).create_template(record, report_xmlid, document_label, filename_parts, pdf_content=pdf_content)
    record.with_context(skip_construction_sign_reset=True).write({
        "sign_template_id": template.id,
        "signing_workflow_id": workflow.id,
        "signature_state": "pending",
        "signature_status_text": status,
        "signature_completed_count": 0,
        "signature_total_count": len(workflow.step_ids),
    })
    first = workflow.step_ids.sorted("sequence")[0]
    record.message_post(
        body=_("%(document)s prepared for signing. Workflow: %(workflow)s. First signer: %(role)s (%(user)s).") % {
            "document": document_label,
            "workflow": workflow.name,
            "role": first.name,
            "user": first.signer_user_id.name,
        }
    )
    action = {
        "type": "ir.actions.act_url",
        "url": f'/odoo/sign/{template.id}/action-sign.Template?id={template.id}',
        "target": "self",
    }
    if issues:
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Placement review required · Not sent"),
            "message": " ".join(issues) + " " + _("Adjust fields in the template, then use Send."),
            "type": "warning", "sticky": True, "next": action,
        }}
    return action


def _open_signature(record):
    record.ensure_one()
    return record.env["absar.sign.workflow.service"].open_status(record)


class ConstructionContract(models.Model):
    _inherit = "construction.contract"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    sign_request_id = fields.Many2one("sign.request", copy=False, readonly=True)
    signing_workflow_id = fields.Many2one("absar.sign.workflow", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    signature_status_text = fields.Char(default="Not Sent", copy=False, readonly=True)
    signature_completed_count = fields.Integer(default=0, copy=False, readonly=True)
    signature_total_count = fields.Integer(default=0, copy=False, readonly=True)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_open_signature_status(self):
        return _open_signature(self)


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

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {
            "project_id", "partner_id", "contract_direction", "customer_reference", "scope",
            "date_start", "date_end", "original_amount", "payment_term_id",
            "retention_percent", "advance_percent", "vat_percent", "notes",
        }
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("Contract modified after signing/sending."))
        return res

    @api.model
    def _cron_sync_construction_sign_status(self):
        service = self.env["absar.sign.workflow.service"]
        for model_name in ("construction.contract", "construction.measurement", "construction.ipc"):
            records = self.env[model_name].search([
                ("sign_template_id", "!=", False),
                ("signature_state", "in", ["pending", "director_pending", "ceo_pending"]),
            ])
            for rec in records:
                service.sync_record(rec, "skip_construction_sign_reset")


class ConstructionMeasurement(models.Model):
    _inherit = "construction.measurement"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    sign_request_id = fields.Many2one("sign.request", copy=False, readonly=True)
    signing_workflow_id = fields.Many2one("absar.sign.workflow", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    signature_status_text = fields.Char(default="Not Sent", copy=False, readonly=True)
    signature_completed_count = fields.Integer(default=0, copy=False, readonly=True)
    signature_total_count = fields.Integer(default=0, copy=False, readonly=True)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_open_signature_status(self):
        return _open_signature(self)


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

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {"contract_id", "contract_order_id", "date", "period_from", "period_to", "prepared_by", "checked_by"}
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("Measurement modified after signing/sending."))
        return res


class ConstructionIPC(models.Model):
    _inherit = "construction.ipc"

    sign_template_id = fields.Many2one("sign.template", copy=False, readonly=True)
    sign_request_id = fields.Many2one("sign.request", copy=False, readonly=True)
    signing_workflow_id = fields.Many2one("absar.sign.workflow", copy=False, readonly=True)
    signature_state = fields.Selection(SIGNATURE_STATES, default="draft", tracking=True, copy=False)
    signature_status_text = fields.Char(default="Not Sent", copy=False, readonly=True)
    signature_completed_count = fields.Integer(default=0, copy=False, readonly=True)
    signature_total_count = fields.Integer(default=0, copy=False, readonly=True)
    revision = fields.Integer(default=0, tracking=True, copy=False)

    def action_open_signature_status(self):
        return _open_signature(self)


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

    def write(self, vals):
        previous = {rec.id: rec.signature_state for rec in self}
        res = super().write(vals)
        if self.env.context.get("skip_construction_sign_reset"):
            return res
        meaningful = {
            "contract_id", "contract_order_id", "measurement_id", "ipc_date",
            "period_from", "period_to", "deduct_advance", "deduct_retention_on_invoice", "deduction_amount",
        }
        if meaningful.intersection(vals):
            for rec in self:
                if previous.get(rec.id) in ACTIVE_SIGNATURE_STATES:
                    _reset_signature(rec, _("IPC modified after signing/sending."))
        return res


class ConstructionContractBOQLine(models.Model):
    _inherit = "construction.contract.boq.line"

    def _reset_parent_contract_signatures(self, states=None, reason=None):
        for contract in self.mapped("contract_id"):
            expected = states.get(contract.id) if states else contract.signature_state
            if expected in ACTIVE_SIGNATURE_STATES:
                _reset_signature(contract, reason or _("Contract BOQ changed after signing/sending."))

    def write(self, vals):
        states = {line.contract_id.id: line.contract_id.signature_state for line in self if line.contract_id}
        res = super().write(vals)
        meaningful = {"sequence", "display_type", "item_code", "description", "uom_id", "contract_qty", "unit_rate"}
        if not self.env.context.get("skip_construction_sign_reset") and meaningful.intersection(vals):
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
        meaningful = {"boq_line_id", "measurement_line_id", "previous_qty", "current_qty", "cumulative_qty", "unit_rate"}
        if not self.env.context.get("skip_construction_sign_reset") and meaningful.intersection(vals):
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
