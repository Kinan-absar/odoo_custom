# Offline Sales checks

Run test_sales_fixes.py with the base and Sales Data Bridge addon folders alongside
each other. PBW_ADDON_PATH and PBW_SALES_BRIDGE_PATH can override the paths. These
checks execute actual methods with controlled ORM fixtures, not an Odoo registry.
Original guard snippets and preservation hashes make the tested source contracts
reproducible without the original full addon archive.

Browser fixture: requires Playwright and /usr/bin/chromium. Run browser_sales.py.
It mounts the shipped line editor with mocked HTTP save/preview responses. It is
not a full portal layout or native tax-computation test. PBW_QA_OUTPUT controls
the output directory. No production code is replaced by the fixture.

Real Odoo cases are separately supplied under tests/test_sales_policy.py, tagged
pbw_sales_policy. They were NOT executed in the packaging environment.
