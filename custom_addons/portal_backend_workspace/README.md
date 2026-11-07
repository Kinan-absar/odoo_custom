# Portal Backend Workspace — Consolidation engineering candidate

This build consolidates original Sales, Purchase, Accounting and HR source files into a single technical addon, and includes the original Employee Portal Suite implementation internally as a compatibility foundation. It is NOT a verified standalone installable product and is NOT a customer release. Employee Portal Suite business routes/models are still present internally; a true extraction of shell-only code remains to do.

## Restrictions
- Do not install in production.
- Do not install alongside the original EPS and original workspace modules; identifiers/routes/models overlap.
- The external Odoo addons listed in the manifest remain required, including custom construction, proposal, treasury and partner modules. This is not yet independent from those engines.
- No Odoo runtime installation has been performed; syntax checks do not prove successful install or working flows.
- User roles, QWeb view inheritance and cross-addon XML references need review.

## Source versions
- Sales 18.0.1.4.14
- Purchase 18.0.1.7.4
- Accounting 18.0.1.3.9
- HR Admin 18.0.1.0.17

## What changed
Original source remains grouped in `components/` with assets under `static/src/`. Module-qualified IDs have been namespaced under `portal_backend_workspace`; native module names in python `odoo.addons` imports and asset URLs were adjusted.

## Next engineering tasks
1. Install in a disposable Odoo 18 Dev clone and fix failures from dependency and view load order.
2. Extract only EPS portal shell to remove EPS business models and routes.
3. Move business workspaces under `/my/workspace` without competing redirects.
4. Remove residual external custom dependencies by isolating related functionality or merging its engine.
5. Test every screen/action/approval, company rules, portal access and notifications.
