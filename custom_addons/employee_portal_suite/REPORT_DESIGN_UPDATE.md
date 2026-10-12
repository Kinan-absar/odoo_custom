# Request printouts — 18.0.1.20.97

Both request printouts now share a navy/teal design with a clear title, request number, actual stage label, two-column request summary, readable tables, and a detailed approval history. Material lines are numbered, quantities aligned, units compact, with white rows and repeating table headers. Employee Requests include project, direct manager, request type and leave dates/type when relevant. Multi-line descriptions and comments are preserved.

Dynamic approval histories show each configured stage, status, eligible approvers or actual actor, decision dates, correction reasons and override remarks. Legacy records retain their recorded approvers/comments and rejection details. Unrecorded decisions are not presented as completed approvals.

The existing ABSAR company header/footer remain provided by Odoo external_layout. Existing report action IDs and filenames are retained; this update adds no duplicate print actions. Report documents use the standard HTML container and per-record external layout for batch printing.

This package is based on version 92: compact colored list badges are included; version 91's company fallback is excluded as requested. Approval execution, access rules and project/company mappings are unchanged.

## Install and verify

Replace employee_portal_suite, commit/push to staging, upgrade Employee Portal Suite, and refresh. Print MR-00741, a material request with many lines, an Employee Request, and a leave request. Also print approved, rejected and returned records. Check company header/footer, current stage, notes and page breaks. Verify batch printing if used.

## Validation

Python/XML checks passed. Both actual report template bodies were rendered offline with dynamic, legacy, rejected, returned, approved and long-content fixture data. Sample PDFs were inspected, and long material lists repeated table headers correctly. The review samples use the supplied MR-00724 company header/footer; production company branding comes from Odoo. Odoo/wkhtmltopdf rendering still needs staging verification after upgrade.

Version 94 fixes QWeb compilation by rendering table-cell fields inside spans rather than on td elements. The print design is unchanged.

Version 95 increases print fonts, removes all heading-table borders, keeps the document heading on one line, and places summary, materials/details and approval history in white cards. Dark table headers, striped rows and summary cell gridlines are removed.

The first request-summary card uses slightly smaller labels and values (10px / 13px), while materials, details and approval-history typography stays larger.

Version 96 removes document subtitles, replaces the heading table with borderless blocks, applies inline border resets to tables and their rows/cells to defeat external-layout grid rules, and increases print typography. Only the white card outline and horizontal material/approval separators remain. Odoo PDF verification after upgrade is still required.


Version 97 applies the ABSAR teal accent card treatment to Material Request and Employee Request printouts: a 6px teal left accent, a thin teal outline on the other sides, 16px rounded corners and a soft teal shadow. Request fields, approval history and table content are unchanged. Odoo PDF rendering after upgrade remains to be verified.
