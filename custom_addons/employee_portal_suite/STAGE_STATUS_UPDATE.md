# Approval badge layout — 18.0.1.20.92

Based on version 90, as requested. This update reduces stage badges to 12px text with 20px total height at the default root font size, lighter weight and smaller padding. It centers the widget and its table cell vertically, prevents wrapping, and preserves the full label in the hover tooltip.

Colors and approval logic are unchanged from version 90. This package does not include version 91's company-fallback change. Assign the correct company to the affected projects.

Replace the employee_portal_suite folder, commit/push, upgrade Employee Portal Suite on staging, then refresh the browser to load the new styling. Check Employee Requests and Material Requests lists, long stage labels, and form badges.

Python/XML and JavaScript syntax checks passed. Live Odoo display verification requires upgrading staging.
