# Aurora Website Theme for Odoo 18

Technical module name: `theme_mytheme`

## Repository layout

Place the folder directly in the root of your Odoo.sh Git repository:

```text
your-repository/
└── theme_mytheme/
    ├── __init__.py
    ├── __manifest__.py
    ├── static/
    └── views/
```

Do not commit the ZIP and do not nest the module inside another
`theme_mytheme` directory.

## Deploy on Odoo.sh

1. Copy `theme_mytheme` into the repository root.
2. Commit and push to the intended Odoo.sh branch.
3. Wait for the build to complete successfully.
4. In Apps, run **Update Apps List**.
5. Search for **Aurora Website Theme** or `theme_mytheme`.
6. Install it, or upgrade it after later changes.

The manifest uses `application: True`, so the module is visible with the normal
Apps filter.

## Odoo.sh shell checks

```python
from odoo.modules.module import get_module_path, get_manifest
get_module_path("theme_mytheme")
get_manifest("theme_mytheme")
```

A valid deployment returns a path under `/home/odoo/src/user/` and a manifest
dictionary.

Refresh the module list from the Odoo shell:

```python
env["ir.module.module"].update_list()
env.cr.commit()
```

Inspect the module record:

```python
module = env["ir.module.module"].search([("name", "=", "theme_mytheme")], limit=1)
module.read(["name", "display_name", "state", "application", "latest_version"])
```

## Upgrade after changes

Increase the version in `__manifest__.py`, push the commit, then upgrade:

```bash
odoo-update theme_mytheme
```

Test on staging before production.
