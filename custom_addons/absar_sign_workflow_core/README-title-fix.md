# ABSAR Sign Workflow Core — 18.0.1.0.16

Remove the standalone `PO -` document label from purchase-order signing titles. A title such as `PO - PO 238 - Supplier - MR - Project` now reads `PO 238 - Supplier - MR - Project`. Supplier, MR, project, revision and filename order remain unchanged. Other document models keep their existing labels.

Replace the existing `absar_sign_workflow_core` folder and upgrade ABSAR Sign Workflow Core on staging. Keep the report-suite and Send to Sign PO modules installed.

The upgrade also renames existing unsigned PO templates when their names exactly start with `PO - ` followed by their source PO name. Matching attachment names and active request references are updated. Completed signed documents, canceled/refused request references and unrelated titles are left unchanged. The PDF content and signing workflow are not changed.

Offline checks passed for Python/XML syntax, title formatting, and upgrade behavior with unsigned, signed and unrelated fixtures. This version has not been run in a live Odoo instance.
