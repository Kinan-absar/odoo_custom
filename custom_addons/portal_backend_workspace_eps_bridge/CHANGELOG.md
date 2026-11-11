# 18.0.0.9.5 - consolidate integrations into the existing bridge

- Added models/sales_data.py from Sales Data Bridge v0.9.5 without modifying its logic.
- Imported the Sales adapter alongside the existing users/notification extensions.
- Kept technical module name, dependencies, auto-install policy, controllers,
  notification provider, templates, XML identifiers and JavaScript unchanged.
- Updated version, summary, installation instructions and offline tests.
- Does not change the accepted main module v0.9.5.
