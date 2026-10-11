# Request printouts — 18.0.1.20.93

Both request printouts now share a navy/teal design with a clear title, request number, actual stage label, two-column request summary, readable tables, and a detailed approval history. Material lines are numbered, quantities aligned, units compact, with alternating row backgrounds and repeating table headers. Employee Requests include project, direct manager, request type and leave dates/type when relevant. Multi-line descriptions and comments are preserved.

Dynamic approval histories show each configured stage, status, eligible approvers or actual actor, decision dates, correction reasons and override remarks. Legacy records retain their recorded approvers/comments and rejection details. Unrecorded decisions are not presented as completed approvals.

The existing ABSAR company header/footer remain provided by Odoo external_layout. Existing report action IDs and filenames are retained; this update adds no duplicate print actions. Report documents use the standard HTML container and per-record external layout for batch printing.

This package is based on version 92: compact colored list badges are included; version 91's company fallback is excluded as requested. Approval execution, access rules and project/company mappings are unchanged.

## Install and verify

Replace employee_portal_suite, commit/push to staging, upgrade Employee Portal Suite, and refresh. Print MR-00741, a material request with many lines, an Employee Request, and a leave request. Also print approved, rejected and returned records. Check company header/footer, current stage, notes and page breaks. Verify batch printing if used.

## Validation

Python/XML checks passed. Both actual report template bodies were rendered offline with dynamic, legacy, rejected, returned, approved and long-content fixture data. Sample PDFs were inspected, and long material lists repeated table headers correctly. The offline renderer uses a sample company header/footer; production company branding comes from Odoo. Odoo/wkhtmltopdf rendering still needs staging verification after upgrade.
