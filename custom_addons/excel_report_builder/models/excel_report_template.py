from ast import literal_eval
from datetime import date, datetime

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


FILTER_OPERATORS = [
    ("=", "is equal to"),
    ("!=", "is not equal to"),
    (">", "is greater than"),
    (">=", "is greater than or equal to"),
    ("<", "is less than"),
    ("<=", "is less than or equal to"),
    ("ilike", "contains"),
    ("not ilike", "does not contain"),
    ("in", "is in"),
    ("not in", "is not in"),
    ("=", "is set / boolean"),
]


class ExcelReportTemplate(models.Model):
    _name = "excel.report.template"
    _description = "Excel Report Template"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    description = fields.Text()

    model_id = fields.Many2one(
        "ir.model",
        string="Odoo Model",
        required=True,
        ondelete="cascade",
        domain="[('transient', '=', False)]",
    )
    model_name = fields.Char(related="model_id.model", store=True, readonly=True)

    column_ids = fields.One2many(
        "excel.report.column", "report_id", string="Columns", copy=True
    )
    filter_ids = fields.One2many(
        "excel.report.filter", "report_id", string="Saved Filters", copy=True
    )

    domain_expression = fields.Char(
        string="Additional Domain",
        default="[]",
        help="Optional Odoo domain, for example [('state', '=', 'posted')].",
    )
    order_by = fields.Char(
        string="Sort Order",
        help="Optional Odoo order expression, for example invoice_date desc, name.",
    )
    max_rows = fields.Integer(
        default=10000,
        help="Safety limit for generated detail rows. Set 0 for no explicit limit.",
    )

    date_field_id = fields.Many2one(
        "ir.model.fields",
        string="Runtime Date Field",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['date', 'datetime']), ('store', '=', True)]",
        help="When set, users can enter From/To dates each time they generate the report.",
    )
    group_field_id = fields.Many2one(
        "ir.model.fields",
        string="Primary Group By",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['one2many', 'many2many', 'binary', 'html']), ('store', '=', True)]",
    )
    second_group_field_id = fields.Many2one(
        "ir.model.fields",
        string="Secondary Group By",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['one2many', 'many2many', 'binary', 'html']), ('store', '=', True)]",
    )
    show_subtotals = fields.Boolean(default=True)
    show_grand_total = fields.Boolean(default=True)

    include_title = fields.Boolean(default=True)
    include_company = fields.Boolean(default=True)
    include_generated_info = fields.Boolean(default=True)
    freeze_header = fields.Boolean(default=True)
    autofilter = fields.Boolean(default=True)
    alternate_rows = fields.Boolean(default=True)
    sheet_name = fields.Char(default="Report")

    state = fields.Selection(
        [("draft", "Draft"), ("ready", "Ready")], default="draft", required=True
    )

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.date_field_id = False
        self.group_field_id = False
        self.second_group_field_id = False
        self.column_ids = [(5, 0, 0)]
        self.filter_ids = [(5, 0, 0)]

    @api.constrains("domain_expression")
    def _check_domain_expression(self):
        for rec in self:
            try:
                domain = literal_eval(rec.domain_expression or "[]")
            except (ValueError, SyntaxError) as exc:
                raise ValidationError(_("Additional Domain is not valid Python domain syntax.")) from exc
            if not isinstance(domain, (list, tuple)):
                raise ValidationError(_("Additional Domain must be a list or tuple."))

    @api.constrains("date_field_id", "group_field_id", "second_group_field_id", "model_id")
    def _check_related_fields_model(self):
        for rec in self:
            for field in (rec.date_field_id, rec.group_field_id, rec.second_group_field_id):
                if field and field.model_id != rec.model_id:
                    raise ValidationError(_("Selected configuration fields must belong to the report model."))

    def action_mark_ready(self):
        for rec in self:
            if not rec.column_ids:
                raise ValidationError(_("Add at least one report column before marking the report Ready."))
            rec.state = "ready"

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_generate(self):
        self.ensure_one()
        if not self.column_ids:
            raise ValidationError(_("Add at least one report column first."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Generate %s", self.name),
            "res_model": "excel.report.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_report_id": self.id},
        }

    def _base_domain(self):
        self.ensure_one()
        try:
            domain = list(literal_eval(self.domain_expression or "[]"))
        except (ValueError, SyntaxError) as exc:
            raise ValidationError(_("Additional Domain is invalid.")) from exc
        domain += self.filter_ids._to_domain()
        return domain


class ExcelReportColumn(models.Model):
    _name = "excel.report.column"
    _description = "Excel Report Column"
    _order = "sequence, id"

    report_id = fields.Many2one("excel.report.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    name = fields.Char(string="Column Header", required=True)
    column_type = fields.Selection(
        [
            ("field", "Odoo Field"),
            ("difference", "Difference (A - B)"),
            ("sum", "Sum (A + B)"),
            ("percentage", "Percentage (A / B × 100)"),
        ],
        default="field",
        required=True,
    )
    model_id = fields.Many2one(
        "ir.model", related="report_id.model_id", store=True, readonly=True
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['one2many', 'binary', 'html']), ('store', '=', True)]",
    )
    source_field_a_id = fields.Many2one(
        "ir.model.fields",
        string="Field A",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['integer', 'float', 'monetary']), ('store', '=', True)]",
    )
    source_field_b_id = fields.Many2one(
        "ir.model.fields",
        string="Field B",
        ondelete="set null",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['integer', 'float', 'monetary']), ('store', '=', True)]",
    )
    width = fields.Float(default=18.0)
    total = fields.Boolean(
        string="Total Column",
        help="Adds subtotal/grand total for numeric values.",
    )
    number_format = fields.Selection(
        [
            ("auto", "Automatic"),
            ("number", "Number"),
            ("integer", "Integer"),
            ("money", "Money"),
            ("percent", "Percent"),
            ("date", "Date"),
            ("datetime", "Date & Time"),
            ("text", "Text"),
        ],
        default="auto",
        required=True,
    )

    @api.onchange("field_id")
    def _onchange_field_id(self):
        if self.field_id and not self.name:
            self.name = self.field_id.field_description

    @api.constrains("field_id", "source_field_a_id", "source_field_b_id", "column_type")
    def _check_column_configuration(self):
        for rec in self:
            if rec.column_type == "field" and not rec.field_id:
                raise ValidationError(_("An Odoo Field is required for normal field columns."))
            if rec.column_type != "field" and (not rec.source_field_a_id or not rec.source_field_b_id):
                raise ValidationError(_("Calculated columns require both Field A and Field B."))
            for f in (rec.field_id, rec.source_field_a_id, rec.source_field_b_id):
                if f and f.model_id != rec.report_id.model_id:
                    raise ValidationError(_("Column fields must belong to the selected report model."))


class ExcelReportFilter(models.Model):
    _name = "excel.report.filter"
    _description = "Excel Report Saved Filter"
    _order = "sequence, id"

    report_id = fields.Many2one("excel.report.template", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    model_id = fields.Many2one(
        "ir.model", related="report_id.model_id", store=True, readonly=True
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        required=True,
        ondelete="cascade",
        domain="[('model_id', '=', model_id), ('ttype', 'not in', ['one2many', 'many2many', 'binary', 'html']), ('store', '=', True)]",
    )
    operator = fields.Selection(
        [
            ("=", "="),
            ("!=", "≠"),
            (">", ">"),
            (">=", "≥"),
            ("<", "<"),
            ("<=", "≤"),
            ("ilike", "contains"),
            ("not ilike", "does not contain"),
            ("in", "in"),
            ("not in", "not in"),
        ],
        default="=",
        required=True,
    )
    value = fields.Char(required=True)

    @api.constrains("field_id")
    def _check_filter_field_model(self):
        for rec in self:
            if rec.field_id and rec.field_id.model_id != rec.report_id.model_id:
                raise ValidationError(_("Filter fields must belong to the selected report model."))

    def _convert_value(self, rec):
        ttype = rec.field_id.ttype
        raw = (rec.value or "").strip()
        if rec.operator in ("in", "not in"):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return [self._convert_scalar(ttype, p) for p in parts]
        return self._convert_scalar(ttype, raw)

    @api.model
    def _convert_scalar(self, ttype, raw):
        if ttype in ("integer", "many2one"):
            try:
                return int(raw)
            except ValueError:
                return raw
        if ttype in ("float", "monetary"):
            try:
                return float(raw)
            except ValueError:
                return raw
        if ttype == "boolean":
            return raw.lower() in ("1", "true", "yes", "y", "on")
        if ttype == "date":
            return fields.Date.to_string(fields.Date.to_date(raw))
        if ttype == "datetime":
            return fields.Datetime.to_string(fields.Datetime.to_datetime(raw))
        if ttype == "selection":
            return raw
        return raw

    def _to_domain(self):
        result = []
        for rec in self.sorted("sequence"):
            result.append((rec.field_id.name, rec.operator, rec._convert_value(rec)))
        return result
