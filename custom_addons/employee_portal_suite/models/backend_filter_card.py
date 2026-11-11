from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.safe_eval import safe_eval
from odoo.osv import expression


class EmployeePortalBackendFilterCard(models.Model):
    _name = "employee.portal.backend.filter.card"
    _description = "Employee Portal Backend Request Filter Card"
    _order = "request_kind, sequence, id"

    request_kind = fields.Selection(
        [("employee", "Employee Requests"), ("material", "Material Requests")],
        required=True,
        index=True,
    )
    filter_type = fields.Selection(
        [("predefined", "Predefined"), ("stage", "Approval Stage"), ("custom", "Custom Domain")],
        required=True,
        default="predefined",
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
        index=True,
    )
    label = fields.Char(required=True, translate=True)
    icon = fields.Char(help="Optional short icon or emoji shown before the card label, for example: ⭐, ⏳, 💰.")
    custom_domain = fields.Text(
        string="Domain",
        help=(
            "Odoo domain used by this custom card. Example: "
            "[('project_id.name', '=', 'TAAKAD')]. "
            "Available variables: uid, company_id."
        ),
    )
    stage_step_ids = fields.Many2many(
        'employee.portal.workflow.step', 'eps_card_workflow_step_rel', 'card_id', 'step_id',
        string='Workflow Steps',
        domain="[('workflow_id.applies_to', '=', 'material_request')]",
        help='Choose current workflow steps; no custom domain is needed.')
    stage_name = fields.Char(string='Stage Name', help='Matches pending snapshot steps by their exact name, including historical steps.')
    auto_stage_key = fields.Char(copy=False, index=True)

    my_requests_only = fields.Boolean(
        string="My Requests Only",
        help="Additionally limit this card to records created by the current logged-in user.",
    )
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
            "Each predefined filter card can only be configured once per request type.",
        )
    ]

    @api.constrains("request_kind", "filter_type", "code", "custom_domain", "stage_step_ids", "stage_name")
    def _check_filter_definition(self):
        er_only = {"manager", "hr", "finance", "leave", "advance", "other"}
        mr_only = {"purchase", "store", "project_manager", "director", "po_required", "no_po_required", "clarification"}
        for rec in self:
            if rec.filter_type == "predefined":
                if not rec.code:
                    raise ValidationError(_("Choose a predefined filter."))
                if rec.request_kind == "employee" and rec.code in mr_only:
                    raise ValidationError(_("This card is only available for Material Requests."))
                if rec.request_kind == "material" and rec.code in er_only:
                    raise ValidationError(_("This card is only available for Employee Requests."))
            elif rec.filter_type == 'stage':
                if rec.request_kind != 'material' or not (rec.stage_step_ids or rec.stage_name):
                    raise ValidationError(_('Select Material Requests and a workflow step or stage name.'))
            else:
                if not (rec.custom_domain or "").strip():
                    raise ValidationError(_("Enter a domain for a custom filter card."))
                rec._evaluate_custom_domain()

    def unlink(self):
        predefined = self.filtered(lambda r: r.filter_type == "predefined")
        if predefined:
            raise UserError(_("Predefined cards cannot be deleted. Disable them instead."))
        return super().unlink()

    @api.model
    def _material_stage_aliases(self):
        return {
            'purchase': ['Purchase Rep', 'Purchase Representative', 'Purchase'],
            'store': ['Store Manager', 'Store'],
            'project_manager': ['Project Manager', 'Project Manager Approval', 'PM'],
            'director': ['Projects Director', 'Project Director', 'Director'],
            'ceo': ['CEO', 'CEO Approval'],
        }

    @api.model
    def _domain_for_code(self, request_kind, code):
        if request_kind == 'material' and code in self._material_stage_aliases():
            names = self._material_stage_aliases()[code]
            steps = expression.OR([[('approval_stage', '=ilike', name)] for name in names])
            return expression.OR([[('state', '=', code)], expression.AND([[('state', '=', 'workflow')], steps])])
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

    def _evaluate_custom_domain(self):
        self.ensure_one()
        source = (self.custom_domain or "[]").strip() or "[]"
        try:
            domain = safe_eval(
                source,
                {
                    "uid": self.env.user.id,
                    "company_id": self.env.company.id,
                },
                mode="eval",
                nocopy=True,
            )
        except Exception as exc:
            raise ValidationError(_("Invalid filter domain: %s") % exc) from exc
        if not isinstance(domain, (list, tuple)):
            raise ValidationError(_("The filter domain must evaluate to a list or tuple."))
        return list(domain)

    def _expand_material_stage_domain(self, domain):
        """Keep existing simple state cards useful with configurable workflows.

        Replace only known MR approval-state leaves; preserve all other filters
        and boolean operators (project, creator, company, etc.).
        """
        aliases = self._material_stage_aliases()
        result = []
        for token in domain:
            if isinstance(token, (tuple, list)) and len(token) == 3 and token[0] == 'state':
                field, operator, value = token
                if operator == '=' and isinstance(value, str) and value in aliases:
                    result.extend(self._domain_for_code('material', value))
                    continue
                if operator == 'in' and isinstance(value, (tuple, list)) and any(code in aliases for code in value):
                    result.extend(expression.OR([self._domain_for_code('material', code) if code in aliases else [('state', '=', code)] for code in value]))
                    continue
            result.append(token)
        return result

    def _get_domain(self):
        self.ensure_one()
        if self.filter_type == 'stage':
            choices = []
            names = list(set(self.stage_step_ids.mapped('name') + ([self.stage_name] if self.stage_name else [])))
            if names:
                choices.extend([[('approval_stage', '=ilike', name)] for name in names])
            domain = expression.AND([[('state', '=', 'workflow')], expression.OR(choices or [[('id', '=', 0)]])])
        elif self.filter_type == "custom":
            domain = self._evaluate_custom_domain()
            if self.request_kind == 'material':
                domain = self._expand_material_stage_domain(domain)
        else:
            domain = self._domain_for_code(self.request_kind, self.code)
        if self.my_requests_only and not (self.filter_type == "predefined" and self.code == "my"):
            domain = list(domain) + [("create_uid", "=", self.env.user.id)]
        return domain

    def action_test_filter(self):
        self.ensure_one()
        model_name = "employee.request" if self.request_kind == "employee" else "material.request"
        domain = self._get_domain()
        try:
            count = self.env[model_name].search_count(domain)
        except Exception as exc:
            raise UserError(_("The domain could not be applied to %s: %s") % (model_name, exc)) from exc
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Filter is valid"),
                "message": _("This card currently matches %s record(s).") % count,
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def action_refresh_material_stage_cards(self, record_ids=None):
        # List-header object buttons pass an ID list to @api.model methods.
        # Upgrade XML calls pass none; this action refreshes shared cards in either case.
        # Normal users may read cards, but cannot change the shared configuration.
        self.check_access_rights('write')
        # Repair labels stored by older revisions from the actual pending snapshot.
        # This changes display/search metadata only, never approvers or workflow states.
        workflow_requests = self.env['material.request'].search([('state', '=', 'workflow')])
        workflow_requests._compute_approval_stage()
        aliases = self._material_stage_aliases()
        labels = {'purchase': 'Purchase Rep', 'store': 'Store Manager', 'project_manager': 'Project Manager',
                  'director': 'Projects Director', 'ceo': 'CEO Approval'}
        styles = {'purchase': 'blue', 'store': 'teal', 'project_manager': 'orange', 'director': 'indigo', 'ceo': 'purple'}
        for index, code in enumerate(aliases):
            card = self.with_context(active_test=False).search([('request_kind', '=', 'material'), ('code', '=', code)], limit=1)
            values = dict(request_kind='material', filter_type='predefined', code=code, active=True)
            if card:
                card.write(values)
            else:
                self.create(dict(values, label=labels[code], sequence=30+index*10, color_style=styles[code]))
        steps = self.env['employee.portal.workflow.step'].search([
            ('workflow_id.applies_to', '=', 'material_request'), ('workflow_id.active', '=', True),
            ('workflow_id.is_template', '=', False),
        ], order='sequence,id')
        names = set(steps.mapped('name'))
        # Keep cards for in-flight snapshots even when the original step was removed.
        names.update(workflow_requests.mapped('approval_stage'))
        known = {name.strip().casefold() for values in aliases.values() for name in values}
        for index, name in enumerate(sorted(n for n in names if n and n.strip().casefold() not in known)):
            key = name.strip().casefold()
            card = self.with_context(active_test=False).search([('request_kind', '=', 'material'), ('auto_stage_key', '=', key)], limit=1)
            values = dict(request_kind='material', filter_type='stage', stage_name=name,
                          stage_step_ids=[(6, 0, steps.filtered(lambda step: step.name == name).ids)], auto_stage_key=key)
            if card:
                card.write(values)
            else:
                self.create(dict(values, label=name, sequence=45+index, color_style='indigo'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('MR Stage Cards'), 'message': _('Stage cards are ready. Reopen Material Requests to use them.'),
            'type': 'success', 'sticky': False}}

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
            try:
                domain = card._get_domain()
                count = request_model.search_count(domain)
            except Exception:
                # A bad custom domain should not break the whole request list.
                continue
            result.append({
                "id": card.id,
                "code": card.code or "custom_%s" % card.id,
                "label": card.label,
                "icon": card.icon or "",
                "sequence": card.sequence,
                "style": card.color_style,
                "domain": domain,
                "count": count,
            })
        return result
