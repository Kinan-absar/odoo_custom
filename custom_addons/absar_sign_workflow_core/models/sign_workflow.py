import base64

from odoo import Command, api, fields, models, _
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

    @api.model
    def _relocate_menu_into_sign_configuration(self):
        """Keep Signing Workflows inside Odoo Sign > Configuration.

        We resolve the Sign configuration menu dynamically instead of depending
        on an Enterprise XML ID that can differ between minor builds.  The
        temporary ABSAR root remains defined only as an upgrade-safe fallback
        and is hidden once relocation succeeds.
        """
        Menu = self.env["ir.ui.menu"].sudo()
        Data = self.env["ir.model.data"].sudo()
        workflow_menu = self.env.ref(
            "absar_sign_workflow_core.menu_absar_signing_workflows",
            raise_if_not_found=False,
        )
        absar_root = self.env.ref(
            "absar_sign_workflow_core.menu_absar_document_signing_root",
            raise_if_not_found=False,
        )
        if not workflow_menu:
            return False

        configuration = Menu.browse()
        candidates = Data.search([
            ("module", "=", "sign"),
            ("model", "=", "ir.ui.menu"),
        ])
        menus = Menu.browse(candidates.mapped("res_id")).exists()
        configuration = menus.filtered(lambda m: (m.name or "").strip().lower() == "configuration")[:1]

        if not configuration:
            sign_roots = menus.filtered(
                lambda m: not m.parent_id and (m.name or "").strip().lower() == "sign"
            )
            if not sign_roots:
                sign_roots = Menu.search([
                    ("parent_id", "=", False),
                    ("name", "=", "Sign"),
                ], limit=1)
            if sign_roots:
                configuration = Menu.search([
                    ("parent_id", "=", sign_roots[:1].id),
                    ("name", "=", "Configuration"),
                ], limit=1)

        if configuration:
            workflow_menu.write({"parent_id": configuration.id, "sequence": 90})
            if absar_root and "active" in absar_root._fields:
                absar_root.write({"active": False})
            return True
        return False

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
        domain=[("active", "=", True)],
        help="Internal and portal users can both be selected. Odoo Sign sends the request to the selected user's contact/email.",
    )
    signer_partner_id = fields.Many2one(
        "res.partner", related="signer_user_id.partner_id", store=True, readonly=True
    )
    sign_role_id = fields.Many2one(
        "sign.item.role",
        string="Odoo Sign Role",
        help="Automatically created/reused from the workflow role name. You can still choose a different Odoo Sign role manually when needed.",
    )

    def _ensure_sign_role(self):
        """Return a concrete Odoo Sign role for this business workflow step."""
        self.ensure_one()
        if self.sign_role_id:
            return self.sign_role_id
        Role = self.env["sign.item.role"].sudo()
        role = Role.search([("name", "=", self.name)], limit=1)
        if not role:
            role = Role.create({"name": self.name})
        self.sudo().sign_role_id = role.id
        return role


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
    def _prepare_template_signature_items(self, template, workflow):
        """Create movable Signature + Date pairs for every configured signer.

        Both fields are assigned to the exact same Odoo Sign role, so once the
        user positions the pair on the PDF there is nothing else to configure.
        The positions are only a staging layout on page 1 and can be dragged to
        the desired location before sending.
        """
        ItemType = self.env["sign.item.type"].sudo()
        signature_type = self.env.ref(
            "sign.sign_item_type_signature", raise_if_not_found=False
        )
        if not signature_type:
            signature_type = ItemType.search([
                ("name", "ilike", "signature")
            ], limit=1)
        if not signature_type:
            raise UserError(_("Odoo Sign signature field type could not be found."))

        # Odoo normally exposes this XML ID.  The name lookup is kept as a
        # compatibility fallback for minor Odoo 18 builds/localizations.
        date_type = self.env.ref(
            "sign.sign_item_type_date", raise_if_not_found=False
        )
        if not date_type:
            date_type = ItemType.search([
                "|",
                ("name", "=ilike", "Date"),
                ("name", "ilike", "date"),
            ], limit=1)
        if not date_type:
            raise UserError(_("Odoo Sign date field type could not be found."))

        SignItem = self.env["sign.item"].sudo()
        for index, step in enumerate(workflow.step_ids.sorted("sequence")):
            role = step._ensure_sign_role()

            # Each signer gets a compact pair in a staging grid:
            # [ Signature ]
            # [ Date      ]
            # The document owner only needs to drag the pair into place.
            row = index % 5
            col = min(index // 5, 2)
            base_x = 0.04 + (0.31 * col)
            base_y = 0.035 + (0.185 * row)

            common = {
                "template_id": template.id,
                "required": True,
                "responsible_id": role.id,
                "page": 1,
                "posX": base_x,
            }
            SignItem.create({
                **common,
                "type_id": signature_type.id,
                "posY": base_y,
                "width": 0.25,
                "height": 0.065,
                "name": _("%(seq)s. %(role)s - Signature") % {
                    "seq": index + 1,
                    "role": step.name,
                },
            })
            SignItem.create({
                **common,
                "type_id": date_type.id,
                "posY": base_y + 0.072,
                "width": 0.16,
                "height": 0.035,
                "name": _("%(seq)s. %(role)s - Date") % {
                    "seq": index + 1,
                    "role": step.name,
                },
            })

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
        self._prepare_template_signature_items(template, workflow)
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

        def _is_completed(item):
            # Odoo 18 normally uses `completed`; keep `signed` as a safe
            # compatibility value for databases/customizations that expose it.
            if "state" in item._fields and item.state in ("completed", "signed"):
                return True
            for field_name in ("is_signed", "signed", "completed"):
                if field_name in item._fields and bool(item[field_name]):
                    return True
            return False

        completed_items = items.filtered(_is_completed)

        if not workflow:
            record.with_context(**{skip_context_key: True}).write({
                "signature_state": "pending",
                "signature_completed_count": len(completed_items),
                "signature_status_text": _("Signing in Progress"),
            })
            return

        steps = workflow.step_ids.sorted("sequence")

        # A sign.request.item represents a signer, not an individual signature
        # box. Counting completed request items is therefore the reliable source
        # of progress. The old implementation required an exact partner+role
        # match and could get stuck at 1/N when Odoo stored the next signer with
        # slightly different metadata. Odoo's send wizard already enforces the
        # configured signer ordering (mail_sent_order when available), so the
        # count maps directly onto our ordered workflow steps.
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


    @api.model
    def get_latest_request(self, record):
        record.ensure_one()
        if "sign_request_id" in record._fields and record.sign_request_id:
            return record.sign_request_id.exists()
        if not getattr(record, "sign_template_id", False):
            return self.env["sign.request"]
        request = self.env["sign.request"].search(
            [("template_id", "=", record.sign_template_id.id)], order="id desc", limit=1
        )
        if request and "sign_request_id" in record._fields:
            record.sudo().write({"sign_request_id": request.id})
        return request

    @api.model
    def open_status(self, record):
        """Open the existing Sign Request once one exists.

        Before the request is sent, open the generated template so the owner can
        position the pre-created signature placeholders. This prevents the status
        smart button from repeatedly reopening the template/sign-from-scratch flow
        after a real Sign Request has already been created.
        """
        record.ensure_one()
        request = self.get_latest_request(record)
        if request:
            return {
                "type": "ir.actions.act_window",
                "name": _("Signature Request"),
                "res_model": "sign.request",
                "res_id": request.id,
                "view_mode": "form",
                "target": "current",
            }
        template = getattr(record, "sign_template_id", False)
        if template:
            return {
                "type": "ir.actions.act_url",
                "url": f"/odoo/sign/{template.id}/action-sign.Template?id={template.id}",
                "target": "self",
            }
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Signature"),
                "message": _("This document has not been prepared for signing yet."),
                "type": "info",
                "sticky": False,
            },
        }


class SignSendRequest(models.TransientModel):
    _inherit = "sign.send.request"

    @api.model
    def _absar_enable_signing_order_vals(self, vals):
        """Enable Odoo Sign's ordering toggle across Odoo 18 minor schemas.

        The signer rows already receive mail_sent_order = 1..N.  Odoo has used
        different boolean field names for the UI toggle across editions/minor
        versions, so set whichever one exists instead of hard-coding one name.
        """
        for field_name in (
            "signing_order",
            "sign_order",
            "set_sign_order",
            "use_sign_order",
            "is_sign_order",
        ):
            if field_name in self._fields:
                vals[field_name] = True
        return vals

    def _absar_enable_signing_order_record(self):
        for wizard in self:
            values = {}
            wizard._absar_enable_signing_order_vals(values)
            for field_name, value in values.items():
                wizard[field_name] = value

    @api.model
    def _absar_signer_commands(self, template):
        workflow = template.absar_workflow_id if template else False
        if not workflow:
            return []
        workflow._validate_configuration()
        Signer = self.env["sign.send.request.signer"]
        commands = [Command.clear()]
        for order, step in enumerate(workflow.step_ids.sorted("sequence"), start=1):
            role = step._ensure_sign_role()
            vals = {
                "role_id": role.id,
                "partner_id": step.signer_partner_id.id,
            }
            # Odoo 18 exposes this on the send wizard when signing order is used.
            # Checking dynamically keeps this bridge safe if a minor edition has
            # a different transient schema.
            if "mail_sent_order" in Signer._fields:
                vals["mail_sent_order"] = order
            commands.append(Command.create(vals))
        return commands

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        template_id = vals.get("template_id") or self.env.context.get("default_template_id")
        if not template_id and self.env.context.get("active_model") == "sign.template":
            template_id = self.env.context.get("active_id")
        if template_id and "signer_ids" in self._fields:
            template = self.env["sign.template"].browse(template_id).exists()
            if template and template.absar_workflow_id:
                vals["template_id"] = template.id
                vals["signer_ids"] = self._absar_signer_commands(template)
                self._absar_enable_signing_order_vals(vals)
                # ABSAR workflows are remote/separate-person signing flows, not
                # Odoo's in-person "Sign Now / Next signatory" flow.
                if "is_user_signer" in self._fields:
                    vals["is_user_signer"] = False
                if "signer_id" in self._fields:
                    vals["signer_id"] = (
                        template.absar_workflow_id.step_ids[:1].signer_partner_id.id
                        if len(template.absar_workflow_id.step_ids) == 1 else False
                    )
        return vals

    @api.onchange("template_id")
    def _onchange_absar_workflow_template(self):
        for wizard in self:
            if not wizard.template_id or not wizard.template_id.absar_workflow_id:
                continue
            if "signer_ids" in wizard._fields:
                wizard.signer_ids = wizard._absar_signer_commands(wizard.template_id)
            wizard._absar_enable_signing_order_record()
            if "is_user_signer" in wizard._fields:
                wizard.is_user_signer = False
            if "signer_id" in wizard._fields:
                wizard.signer_id = (
                    wizard.template_id.absar_workflow_id.step_ids[:1].signer_partner_id
                    if len(wizard.template_id.absar_workflow_id.step_ids) == 1 else False
                )

    @api.model_create_multi
    def create(self, vals_list):
        # Never let ABSAR multi-signer workflows silently become an in-person
        # signing session just because the sender is also one of the signers.
        for vals in vals_list:
            template_id = vals.get("template_id") or self.env.context.get("default_template_id")
            template = self.env["sign.template"].browse(template_id).exists() if template_id else False
            if template and template.absar_workflow_id:
                self._absar_enable_signing_order_vals(vals)
                if "is_user_signer" in self._fields:
                    vals["is_user_signer"] = False
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("is_user_signer"):
            if any(w.template_id.absar_workflow_id for w in self):
                vals = dict(vals, is_user_signer=False)
        return super().write(vals)


class SignTemplate(models.Model):
    _inherit = "sign.template"

    absar_workflow_id = fields.Many2one(
        "absar.sign.workflow", string="ABSAR Signing Workflow", copy=False, readonly=True
    )
    absar_source_model = fields.Char(copy=False, readonly=True)
    absar_source_id = fields.Integer(copy=False, readonly=True)

    def _absar_sync_source_document(self):
        service = self.env["absar.sign.workflow.service"].sudo()
        for template in self.sudo():
            if not template.absar_source_model or not template.absar_source_id:
                continue
            if template.absar_source_model not in self.env:
                continue
            record = self.env[template.absar_source_model].sudo().browse(template.absar_source_id).exists()
            if record and "sign_template_id" in record._fields and record.sign_template_id == template:
                service.sync_record(record, "skip_absar_sign_live_sync")


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    def write(self, vals):
        res = super().write(vals)
        watched = {"state", "partner_id", "role_id"}
        if watched.intersection(vals):
            templates = self.mapped("sign_request_id.template_id").filtered("absar_workflow_id")
            templates._absar_sync_source_document()
        return res


class SignRequest(models.Model):
    _inherit = "sign.request"

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        for request in requests:
            template = request.template_id
            if not template or not template.absar_source_model or not template.absar_source_id:
                continue
            if template.absar_source_model not in self.env:
                continue
            source = self.env[template.absar_source_model].sudo().browse(template.absar_source_id).exists()
            if source and "sign_request_id" in source._fields:
                source.write({"sign_request_id": request.id})
        return requests

    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            self.mapped("template_id").filtered("absar_workflow_id")._absar_sync_source_document()
        return res
