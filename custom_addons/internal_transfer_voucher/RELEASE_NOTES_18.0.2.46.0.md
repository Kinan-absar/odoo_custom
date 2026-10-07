# 18.0.2.46.0 — Payment Review UI fixes

- Apply Selected now returns a notification followed by the existing view's close/reload callback, instead of opening a second Recommendations window action. This is intended to keep the current list, review scope, filters, and breadcrumbs.
- Run / Refresh Review uses the existing form's reload callback instead of reloading the whole Odoo interface.
- Corrected the SCSS selector to target the list root, where Odoo puts o_payment_review_line_list. Native selection checkboxes and data cells now share top alignment and padding.
- No accounting or retention logic changes in this release.

Validation: 33 offline regression checks passed; Python syntax and XML parsing passed. These are local checks, not Odoo integration tests. The new UI behavior requires installation on staging and a browser retest.

See quality_checks/STAGING_RETEST.md for actual browser tests of the upgraded previous release.
