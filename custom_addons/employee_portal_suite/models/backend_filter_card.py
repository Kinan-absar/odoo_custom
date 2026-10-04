from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class EmployeePortalBackendFilterCard(models.Model):
    _name = "employee.portal.backend.filter.card"
    _description = "Employee Portal Backend Request Filter Card"
    _order = "request_kind, sequence, id"

    request_kind = fields.Selection(
        [("employee", "Employee Requests"), ("material", "Material Requests")],
        required=True,
        index=True,
    )
    code = fields.Selection(
        [
            ("all", "All"),
            ("draft", "Draft"),
            ("workflow", "Workflow Approval"),
            ("manager", "Manager Approval"),
            ("hr", "HR Approval"),
            ("finance", "Finance Approval"),
            ("purchase", "Purchase Representative"),
            ("store", "Store Manager"),
            ("project_manager", "Project Manager"),
            ("director", "Director"),
            ("ceo", "CEO Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("leave", "Leave"),
            ("advance", "Salary Advance"),
            ("other", "Other"),
            ("po_required", "PO Required"),
            ("no_po_required", "No PO Required"),
            ("clarification", "Clarification"),
            ("my", "My Requests"),
        ],
        required=True,
        index=True,
    )
    label = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color_style = fields.Selection(
        [
            ("neutral", "Neutral"),
            ("muted", "Muted"),
            ("blue", "Blue"),
            ("teal", "Teal"),
            ("orange", "Orange"),
            ("indigo", "Indigo"),
            ("purple", "Purple"),
            ("green", "Green"),
            ("red", "Red"),
            ("warning", "Warning"),
            ("my", "My Requests"),
        ],
        default="neutral",
        required=True,
    )

    _sql_constraints = [
        (
            "request_kind_code_unique",
            "unique(request_kind, code)",
            "Each filter card can only be configured once per request type.",
        )
    ]

    @api.constrains("request_kind", "code")
    def _check_code_matches_kind(self):
        er_only = {"manager", "hr", "finance", "leave", "advance", "other"}
        mr_only = {"purchase", "store", "project_manager", "director", "po_required", "no_po_required", "clarification"}
        for rec in self:
            if rec.request_kind == "employee" and rec.code in mr_only:
                raise ValidationError(_("This card is only available for Material Requests."))
            if rec.request_kind == "material" and rec.code in er_only:
                raise ValidationError(_("This card is only available for Employee Requests."))

    @api.model
    def _domain_for_code(self, request_kind, code):
        if code == "all":
            return []
        if code == "my":
            return [("create_uid", "=", self.env.user.id)]
        if code == "clarification":
            return [("needs_clarification", "=", True)]
        if code == "po_required":
            return [("no_po_required", "=", False)]
        if code == "no_po_required":
            return [("no_po_required", "=", True)]
        if request_kind == "employee" and code in {"leave", "advance", "other"}:
            return [("request_type", "=", code)]
        state_codes = {
            "draft", "workflow", "manager", "hr", "finance", "purchase", "store",
            "project_manager", "director", "ceo", "approved", "rejected",
        }
        if code in state_codes:
            return [("state", "=", code)]
        return []

    @api.model
    def get_dashboard_cards(self, request_kind):
        if request_kind not in ("employee", "material"):
            return []
        model_name = "employee.request" if request_kind == "employee" else "material.request"
        records = self.search([
            ("request_kind", "=", request_kind),
            ("active", "=", True),
        ], order="sequence,id")
        result = []
        request_model = self.env[model_name]
        for card in records:
            domain = self._domain_for_code(request_kind, card.code)
            result.append({
                "id": card.id,
                "code": card.code,
                "label": card.label,
                "sequence": card.sequence,
                "style": card.color_style,
                "domain": domain,
                "count": request_model.search_count(domain),
            })
        return result
