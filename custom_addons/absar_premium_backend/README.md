# ABSAR Premium Backend — Odoo 18

Initial backend UI redesign for Odoo 18 Enterprise.

## Included in v18.0.1.0.0

- Global design tokens and premium light palette
- Navbar and dropdown refinement
- Control panel and search styling
- Form sheets and section hierarchy
- Input, textarea, many2one, tags, checkbox and readonly treatment
- Primary/secondary button hierarchy
- Pill-style status bar
- Notebook/tab redesign
- List/table refinement
- Kanban card refinement
- Chatter and attachment styling
- Dialog/wizard styling
- Semantic badges
- Mobile/tablet responsive adjustments

## Install

1. Add the `absar_premium_backend` folder to your custom addons repository.
2. Push it to an Odoo.sh development branch.
3. Update the Apps list.
4. Search for `ABSAR Premium Backend` and install it.
5. Hard-refresh the browser after installation so the new asset bundle is loaded.

## Development principle

This module is intentionally presentation-only. It does not alter accounting,
purchase, project, construction, portal, approval or other business logic.
