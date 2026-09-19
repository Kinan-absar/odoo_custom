from odoo import api, models


class AccountStatementNativeReportSetup(models.AbstractModel):
    _name = "account.statement.native.report.setup"
    _description = "Account Statement Native Report Setup"

    @api.model
    def configure_native_report(self):
        """Turn our report into an independent clone of Odoo's Partner Ledger engine.

        A plain ``root_report_id`` only creates a report *variant*. It does not
        clone the Partner Ledger's custom handler or columns, which is why the
        previous build rendered the native toolbar but no lines.

        This setup is executed from XML on every module install/upgrade. It
        copies the runtime configuration that actually drives Partner Ledger
        while keeping our own report record, name, menu and external id.
        """
        source = self.env.ref("account_reports.partner_ledger_report")
        target = self.env.ref("account_statement_reports.account_statement_native_report")

        # First detach from the old variant relationship. Filter fields are
        # computed from root_report_id in Odoo, so do this in a separate write
        # before assigning the copied Partner Ledger options below.
        target.write({
            "name": "Account Statement Reports",
            "root_report_id": False,
        })

        vals = {}

        # Copy the engine / rendering configuration from the installed Odoo 18
        # Partner Ledger. Checking field existence keeps the module resilient to
        # minor Enterprise revisions without hard-coding unavailable fields.
        fields_to_copy = [
            "custom_handler_model_id",
            "main_template",
            "line_template",
            "filter_show_draft",
            "filter_account_type",
            "filter_partner",
            "filter_unfold_all",
            "filter_unreconciled",
            "filter_period_comparison",
            "filter_multi_company",
            "default_opening_date_filter",
            "search_bar",
            "load_more_limit",
        ]
        for field_name in fields_to_copy:
            if field_name in source._fields and field_name in target._fields:
                value = source[field_name]
                field = source._fields[field_name]
                if field.type == "many2one":
                    vals[field_name] = value.id
                else:
                    vals[field_name] = value

        # Our report must be an independent root report, not a country variant.
        if "availability_condition" in target._fields:
            vals["availability_condition"] = "always"
        if "country_id" in target._fields:
            vals["country_id"] = False

        target.write(vals)

        # Partner Ledger is driven by its custom handler *and* its report
        # columns. Variants do not inherit the One2many columns, so clone them.
        target.column_ids.unlink()
        for column in source.column_ids.sorted(lambda c: (c.sequence, c.id)):
            column.copy(default={"report_id": target.id})

        # Partner Ledger lines are generated dynamically by its custom handler,
        # so no static report lines are required here.

        return True
