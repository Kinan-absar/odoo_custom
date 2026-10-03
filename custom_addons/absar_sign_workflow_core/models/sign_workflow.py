import base64

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class AbsarSignWorkflow(models.Model):
    _name = "absar.sign.workflow"
    _description = "Document Signing Workflow"
    _order = "company_id, model_id, project_id, name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Document Model",
        required=True,
        ondelete="cascade",
        help="The business document this signing workflow applies to, such as Purchase Order, Construction Contract, Measurement or IPC.",
    )
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        help="Optional. If set, this workflow is used only for this project. Leave empty to make it the company default for the document type.",
    )
    step_ids = fields.One2many(
        "absar.sign.workflow.step", "workflow_id", string="Signer Steps", copy=True
    )
    step_count = fields.Integer(compute="_compute_step_count")

    @api.depends("step_ids")
    def _compute_step_count(self):
        for rec in self:
            rec.step_count = len(rec.step_ids)

    @api.constrains("active", "company_id", "model_id", "project_id")
    def _check_unique_scope(self):
        for rec in self.filtered("active"):
            domain = [
                ("id", "!=", rec.id),
                ("active", "=", True),
                ("company_id", "=", rec.company_id.id),
                ("model_id", "=", rec.model_id.id),
            ]
            if rec.project_id:
                domain.append(("project_id", "=", rec.project_id.id))
            else:
                domain.append(("project_id", "=", False))
            if self.search_count(domain):
                scope = rec.project_id.display_name if rec.project_id else _("Company Default")
                raise ValidationError(
                    _("Only one active signing workflow is allowed for %(model)s / %(scope)s.")
                    % {"model": rec.model_id.name, "scope": scope}
                )

    def _validate_configuration(self):
        self.ensure_one()
        steps = self.step_ids.sorted("sequence")
        if not steps:
            raise UserError(_("Add at least one signer step before using this workflow."))
        missing = steps.filtered(lambda s: not s.signer_user_id)
        if missing:
            raise UserError(
                _("Every signer step needs a Signer User. Missing: %s")
                % ", ".join(missing.mapped("name"))
            )
        no_email = steps.filtered(lambda s: not s.signer_user_id.partner_id.email)
        if no_email:
            raise UserError(
                _("These signer users do not have an email address: %s")
                % ", ".join(no_email.mapped("signer_user_id.name"))
            )
        return True

    def action_validate_workflow(self):
        self._validate_configuration()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signing Workflow"),
                "message": _("Workflow configuration is valid."),
                "type": "success",
                "sticky": False,
            },
        }


class AbsarSignWorkflowStep(models.Model):
    _name = "absar.sign.workflow.step"
    _description = "Document Signing Workflow Step"
    _order = "sequence, id"

    workflow_id = fields.Many2one(
        "absar.sign.workflow", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10, required=True)
    name = fields.Char(
        string="Signer Role",
        required=True,
        help="Business label displayed in the document status, e.g. Project Director, Commercial Manager or CEO.",
    )
    signer_user_id = fields.Many2one(
        "res.users",
        string="Signer User",
        required=True,
        domain=[("share", "=", False)],
    )
    signer_partner_id = fields.Many2one(
        "res.partner", related="signer_user_id.partner_id", store=True, readonly=True
    )
    sign_role_id = fields.Many2one(
        "sign.item.role",
        string="Odoo Sign Role",
        help="Optional but recommended. When you place signature fields in Odoo Sign, use this same role so signer tracking can match the configured step precisely.",
    )


class AbsarSignWorkflowService(models.AbstractModel):
    _name = "absar.sign.workflow.service"
    _description = "ABSAR Signing Workflow Service"

    @api.model
    def get_workflow(self, record, required=False):
        company = record.company_id if "company_id" in record._fields and record.company_id else self.env.company
        model = self.env["ir.model"]._get(record._name)
        project = record.project_id if "project_id" in record._fields and record.project_id else False

        Workflow = self.env["absar.sign.workflow"]
        workflow = False
        if project:
            workflow = Workflow.search([
                ("active", "=", True),
                ("company_id", "=", company.id),
                ("model_id", "=", model.id),
                ("project_id", "=", project.id),
            ], limit=1)
        if not workflow:
            workflow = Workflow.search([
                ("active", "=", True),
                ("company_id", "=", company.id),
                ("model_id", "=", model.id),
                ("project_id", "=", False),
            ], limit=1)

        if required and not workflow:
            raise UserError(
                _("No signing workflow is configured for %(document)s. Open Document Signing > Signing Workflows and configure the signer chain first.")
                % {"document": model.name}
            )
        if workflow:
            workflow._validate_configuration()
        return workflow

    @api.model
    def create_template(self, record, report_xmlid, document_label, filename_parts):
        record.ensure_one()
        workflow = self.get_workflow(record, required=True)
        pdf_content, pdf_format = self.env["ir.actions.report"]._render_qweb_pdf(
            report_xmlid, record.ids
        )
        clean_parts = [str(part).strip() for part in filename_parts if part and str(part).strip()]
        filename = " - ".join(clean_parts) or record.display_name
        if getattr(record, "revision", 0):
            filename += f"_R{record.revision}"
        filename += ".pdf"

        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "datas": base64.b64encode(pdf_content),
            "type": "binary",
            "mimetype": "application/pdf",
            "res_model": record._name,
            "res_id": record.id,
        })
        template = self.env["sign.template"].create({
            "name": f"{document_label} - {filename[:-4]}",
            "attachment_id": attachment.id,
            "absar_workflow_id": workflow.id,
            "absar_source_model": record._name,
            "absar_source_id": record.id,
        })
        steps = workflow.step_ids.sorted("sequence")
        first = steps[0]
        status = _("0/%(total)s Signed · Waiting: %(role)s") % {
            "total": len(steps), "role": first.name
        }
        return template, workflow, status

    @api.model
    def sync_record(self, record, skip_context_key):
        record.ensure_one()
        template = record.sign_template_id
        if not template:
            return

        workflow = record.signing_workflow_id or self.get_workflow(record, required=False)
        request = self.env["sign.request"].search(
            [("template_id", "=", template.id)], order="id desc", limit=1
        )
        if not request:
            vals = {"signature_status_text": _("Template Ready · Awaiting Send")}
            if workflow:
                vals["signature_total_count"] = len(workflow.step_ids)
            record.with_context(**{skip_context_key: True}).write(vals)
            return

        if request.state in ("canceled", "refused"):
            record.with_context(**{skip_context_key: True}).write({
                "signature_state": "rejected",
                "signature_status_text": _("Rejected"),
            })
            return
        if request.state == "signed":
            total = len(workflow.step_ids) if workflow else 0
            record.with_context(**{skip_context_key: True}).write({
                "signature_state": "signed",
                "signature_completed_count": total,
                "signature_total_count": total,
                "signature_status_text": _("Fully Signed"),
            })
            return

        items = self.env["sign.request.item"].search([("sign_request_id", "=", request.id)])
        completed_items = items.filtered(lambda item: item.state == "completed")

        if not workflow:
            record.with_context(**{skip_context_key: True}).write({
                "signature_state": "pending",
                "signature_completed_count": len(completed_items),
                "signature_status_text": _("Signing in Progress"),
            })
            return

        steps = workflow.step_ids.sorted("sequence")
        completed_count = 0
        partner_field = "partner_id" if "partner_id" in items._fields else False
        role_field = "role_id" if "role_id" in items._fields else False

        for step in steps:
            matched = False
            if partner_field:
                step_items = completed_items.filtered(
                    lambda item: item.partner_id.id == step.signer_partner_id.id
                )
                if step.sign_role_id and role_field:
                    step_items = step_items.filtered(
                        lambda item: item.role_id.id == step.sign_role_id.id
                    )
                matched = bool(step_items)
            if matched:
                completed_count += 1
            else:
                break

        # Backward-compatible fallback for older requests where signer metadata
        # cannot be matched to configured users/roles.
        if completed_count == 0 and completed_items:
            completed_count = min(len(completed_items), len(steps))

        if completed_count >= len(steps):
            status = _("All configured signers completed · Awaiting Sign finalization")
        else:
            current = steps[completed_count]
            status = _("%(done)s/%(total)s Signed · Waiting: %(role)s") % {
                "done": completed_count,
                "total": len(steps),
                "role": current.name,
            }

        record.with_context(**{skip_context_key: True}).write({
            "signature_state": "pending",
            "signature_completed_count": completed_count,
            "signature_total_count": len(steps),
            "signature_status_text": status,
            "signing_workflow_id": workflow.id,
        })


class SignTemplate(models.Model):
    _inherit = "sign.template"

    absar_workflow_id = fields.Many2one(
        "absar.sign.workflow", string="ABSAR Signing Workflow", copy=False, readonly=True
    )
    absar_source_model = fields.Char(copy=False, readonly=True)
    absar_source_id = fields.Integer(copy=False, readonly=True)
