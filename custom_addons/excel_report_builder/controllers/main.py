import io
import re
from datetime import date, datetime

import xlsxwriter

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import AccessError, MissingError, ValidationError
from werkzeug.exceptions import Forbidden, NotFound
from werkzeug.wrappers import Response


INVALID_SHEET_CHARS = re.compile(r"[\\/*?:\[\]]")


class ExcelReportBuilderController(http.Controller):

    @http.route(
        "/excel_report_builder/download/<int:wizard_id>",
        type="http",
        auth="user",
        methods=["GET"],
        csrf=False,
    )
    def download_report(self, wizard_id, **kwargs):
        wizard = request.env["excel.report.wizard"].browse(wizard_id).exists()
        if not wizard:
            raise NotFound()
        try:
            wizard.check_access_rights("read")
            wizard.check_access_rule("read")
            report = wizard.report_id
            report.check_access_rights("read")
            report.check_access_rule("read")
            content = self._build_xlsx(wizard)
        except (AccessError, MissingError):
            raise Forbidden()

        filename = self._safe_filename(report.name) + ".xlsx"
        return request.make_response(
            content,
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", f'attachment; filename="{filename}"'),
                ("Content-Length", str(len(content))),
            ],
        )

    def _build_xlsx(self, wizard):
        report = wizard.report_id
        env = request.env
        if not report.model_name or report.model_name not in env:
            raise ValidationError(_("The configured Odoo model is not available."))

        model = env[report.model_name]
        # Search is deliberately performed in the current user's environment, without sudo,
        # so normal ACLs, record rules, company rules, etc. remain effective.
        domain = report._base_domain()
        if report.date_field_id:
            fname = report.date_field_id.name
            if wizard.date_from:
                if report.date_field_id.ttype == "datetime":
                    domain.append((fname, ">=", fields.Datetime.to_string(datetime.combine(wizard.date_from, datetime.min.time()))))
                else:
                    domain.append((fname, ">=", fields.Date.to_string(wizard.date_from)))
            if wizard.date_to:
                if report.date_field_id.ttype == "datetime":
                    domain.append((fname, "<=", fields.Datetime.to_string(datetime.combine(wizard.date_to, datetime.max.time()))))
                else:
                    domain.append((fname, "<=", fields.Date.to_string(wizard.date_to)))

        limit = report.max_rows if report.max_rows and report.max_rows > 0 else None
        records = model.search(domain, order=report.order_by or None, limit=limit)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        try:
            self._write_workbook(workbook, wizard, records)
        finally:
            workbook.close()
        output.seek(0)
        return output.read()

    def _write_workbook(self, workbook, wizard, records):
        report = wizard.report_id
        columns = report.column_ids.sorted("sequence")
        if not columns:
            raise ValidationError(_("This report does not contain any columns."))

        sheet_name = INVALID_SHEET_CHARS.sub("-", report.sheet_name or report.name or "Report")[:31] or "Report"
        sheet = workbook.add_worksheet(sheet_name)

        fmt_title = workbook.add_format({"bold": True, "font_size": 16})
        fmt_meta = workbook.add_format({"font_size": 9, "italic": True, "font_color": "#666666"})
        fmt_header = workbook.add_format({"bold": True, "border": 1, "bg_color": "#E9EEF5", "align": "center", "valign": "vcenter"})
        fmt_group = workbook.add_format({"bold": True, "bg_color": "#DCE6F1", "top": 1, "bottom": 1})
        fmt_subtotal_label = workbook.add_format({"bold": True, "top": 1})
        fmt_total_label = workbook.add_format({"bold": True, "top": 2, "bottom": 2})
        fmt_text = workbook.add_format({})
        fmt_text_alt = workbook.add_format({"bg_color": "#F8FAFC"})
        fmt_number = workbook.add_format({"num_format": "#,##0.00"})
        fmt_number_alt = workbook.add_format({"num_format": "#,##0.00", "bg_color": "#F8FAFC"})
        fmt_integer = workbook.add_format({"num_format": "#,##0"})
        fmt_integer_alt = workbook.add_format({"num_format": "#,##0", "bg_color": "#F8FAFC"})
        fmt_money = workbook.add_format({"num_format": "#,##0.00"})
        fmt_money_alt = workbook.add_format({"num_format": "#,##0.00", "bg_color": "#F8FAFC"})
        fmt_percent = workbook.add_format({"num_format": "0.00%"})
        fmt_percent_alt = workbook.add_format({"num_format": "0.00%", "bg_color": "#F8FAFC"})
        fmt_date = workbook.add_format({"num_format": "yyyy-mm-dd"})
        fmt_date_alt = workbook.add_format({"num_format": "yyyy-mm-dd", "bg_color": "#F8FAFC"})
        fmt_datetime = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm"})
        fmt_datetime_alt = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm", "bg_color": "#F8FAFC"})
        fmt_subtotal_num = workbook.add_format({"bold": True, "top": 1, "num_format": "#,##0.00"})
        fmt_total_num = workbook.add_format({"bold": True, "top": 2, "bottom": 2, "num_format": "#,##0.00"})

        row = 0
        if report.include_title:
            sheet.merge_range(row, 0, row, max(0, len(columns) - 1), report.name, fmt_title)
            row += 1
        if report.include_company:
            sheet.write(row, 0, request.env.company.display_name, fmt_meta)
            row += 1
        if report.include_generated_info:
            generated = fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now())
            sheet.write(row, 0, _("Generated by %s on %s") % (request.env.user.display_name, generated.strftime("%Y-%m-%d %H:%M")), fmt_meta)
            row += 1
        if wizard.date_from or wizard.date_to:
            period = _("Period: %s to %s") % (wizard.date_from or "…", wizard.date_to or "…")
            sheet.write(row, 0, period, fmt_meta)
            row += 1
        if row:
            row += 1

        header_row = row
        for col_idx, col in enumerate(columns):
            sheet.write(header_row, col_idx, col.name, fmt_header)
            sheet.set_column(col_idx, col_idx, max(6.0, min(col.width or 18.0, 80.0)))
        row += 1

        if report.freeze_header:
            sheet.freeze_panes(row, 0)

        groups = self._group_records(records, report.group_field_id, report.second_group_field_id)
        grand_totals = [0.0 for _ in columns]
        detail_index = 0

        for group_label, subgroup_items in groups:
            if report.group_field_id:
                sheet.merge_range(row, 0, row, max(0, len(columns) - 1), group_label, fmt_group)
                row += 1

            for subgroup_label, group_records in subgroup_items:
                if report.second_group_field_id:
                    sheet.merge_range(row, 0, row, max(0, len(columns) - 1), "  " + subgroup_label, fmt_group)
                    row += 1

                subtotal = [0.0 for _ in columns]
                for record in group_records:
                    alt = report.alternate_rows and (detail_index % 2 == 1)
                    values = []
                    for col_idx, col in enumerate(columns):
                        value = self._column_value(record, col)
                        values.append(value)
                        cell_value, value_kind = self._excel_value(value, col)
                        fmt = self._format_for_kind(value_kind, alt, fmt_text, fmt_text_alt, fmt_number, fmt_number_alt, fmt_integer, fmt_integer_alt, fmt_money, fmt_money_alt, fmt_percent, fmt_percent_alt, fmt_date, fmt_date_alt, fmt_datetime, fmt_datetime_alt)
                        if value_kind == "percent":
                            sheet.write_number(row, col_idx, cell_value / 100.0 if cell_value is not None else 0.0, fmt)
                        elif value_kind in ("number", "integer", "money") and isinstance(cell_value, (int, float)):
                            sheet.write_number(row, col_idx, cell_value, fmt)
                        elif value_kind in ("date", "datetime") and isinstance(cell_value, (date, datetime)):
                            sheet.write_datetime(row, col_idx, cell_value if isinstance(cell_value, datetime) else datetime.combine(cell_value, datetime.min.time()), fmt)
                        else:
                            sheet.write(row, col_idx, cell_value, fmt)

                        if col.total and isinstance(value, (int, float)) and not isinstance(value, bool):
                            subtotal[col_idx] += float(value)
                            grand_totals[col_idx] += float(value)
                    row += 1
                    detail_index += 1

                if report.show_subtotals and (report.group_field_id or report.second_group_field_id) and group_records:
                    sheet.write(row, 0, _("Subtotal"), fmt_subtotal_label)
                    for col_idx, col in enumerate(columns):
                        if col.total:
                            sheet.write_number(row, col_idx, subtotal[col_idx], fmt_subtotal_num)
                    row += 1

        last_data_row = max(header_row, row - 1)
        if report.show_grand_total and records:
            sheet.write(row, 0, _("Grand Total"), fmt_total_label)
            for col_idx, col in enumerate(columns):
                if col.total:
                    sheet.write_number(row, col_idx, grand_totals[col_idx], fmt_total_num)
            row += 1

        if report.autofilter and last_data_row >= header_row:
            sheet.autofilter(header_row, 0, last_data_row, len(columns) - 1)

        sheet.set_row(header_row, 24)

    def _group_records(self, records, group_field, second_group_field):
        if not group_field:
            return [("", [("", records)])]

        first = {}
        for record in records:
            key = self._group_key(record, group_field)
            first.setdefault(key, request.env[record._name])
            first[key] |= record

        result = []
        for key in sorted(first, key=lambda x: str(x).lower()):
            recs = first[key]
            if not second_group_field:
                result.append((str(key), [("", recs)]))
                continue
            second = {}
            for record in recs:
                skey = self._group_key(record, second_group_field)
                second.setdefault(skey, request.env[record._name])
                second[skey] |= record
            result.append((str(key), [(str(skey), second[skey]) for skey in sorted(second, key=lambda x: str(x).lower())]))
        return result

    def _group_key(self, record, field_meta):
        value = record[field_meta.name]
        if field_meta.ttype == "many2one":
            return value.display_name if value else _("Undefined")
        if field_meta.ttype in ("many2many", "one2many"):
            return ", ".join(value.mapped("display_name")) or _("Undefined")
        if field_meta.ttype == "selection":
            return self._selection_label(record, field_meta.name, value) or _("Undefined")
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m-%d")
        return value if value not in (False, None, "") else _("Undefined")

    def _column_value(self, record, col):
        if col.column_type == "field":
            return self._read_value(record, col.field_id)
        a = self._numeric_raw(record, col.source_field_a_id)
        b = self._numeric_raw(record, col.source_field_b_id)
        if col.column_type == "difference":
            return a - b
        if col.column_type == "sum":
            return a + b
        if col.column_type == "percentage":
            return (a / b * 100.0) if b else 0.0
        return ""

    def _numeric_raw(self, record, field_meta):
        value = record[field_meta.name]
        return float(value or 0.0)

    def _read_value(self, record, field_meta):
        value = record[field_meta.name]
        ttype = field_meta.ttype
        if ttype == "many2one":
            return value.display_name if value else ""
        if ttype in ("many2many", "one2many"):
            return ", ".join(value.mapped("display_name"))
        if ttype == "selection":
            return self._selection_label(record, field_meta.name, value)
        if ttype == "boolean":
            return _("Yes") if value else _("No")
        return value if value is not False else ""

    def _selection_label(self, record, field_name, value):
        if not value:
            return ""
        field = record._fields.get(field_name)
        if not field:
            return value
        selection = field._description_selection(record.env)
        return dict(selection).get(value, value)

    def _excel_value(self, value, col):
        if col.column_type == "percentage" or col.number_format == "percent":
            return (float(value or 0.0), "percent")
        if col.number_format != "auto":
            forced = col.number_format
            if forced == "text":
                return ("" if value is None else str(value), "text")
            if forced in ("number", "integer", "money"):
                try:
                    return (float(value or 0.0), forced)
                except (TypeError, ValueError):
                    return (value, "text")
            if forced in ("date", "datetime"):
                return (value, forced)

        if col.column_type == "field" and col.field_id:
            ttype = col.field_id.ttype
            if ttype == "integer":
                return (value or 0, "integer")
            if ttype == "float":
                return (value or 0.0, "number")
            if ttype == "monetary":
                return (value or 0.0, "money")
            if ttype == "date":
                return (value, "date")
            if ttype == "datetime":
                return (value, "datetime")
        if col.column_type in ("difference", "sum"):
            return (value or 0.0, "number")
        return (value, "text")

    def _format_for_kind(self, kind, alt, *formats):
        mapping = {
            "text": (formats[0], formats[1]),
            "number": (formats[2], formats[3]),
            "integer": (formats[4], formats[5]),
            "money": (formats[6], formats[7]),
            "percent": (formats[8], formats[9]),
            "date": (formats[10], formats[11]),
            "datetime": (formats[12], formats[13]),
        }
        normal, alternate = mapping.get(kind, mapping["text"])
        return alternate if alt else normal

    def _safe_filename(self, name):
        cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", name or "report").strip()
        return cleaned.replace(" ", "_") or "report"
