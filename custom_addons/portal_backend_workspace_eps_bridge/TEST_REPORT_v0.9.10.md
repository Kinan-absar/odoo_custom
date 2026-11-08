# Portal Backend Workspace and existing EPS Bridge 18.0.0.9.10

## Requested UI changes
This update is built from the supplied main addon v0.9.7 and existing EPS bridge
v0.9.9. There is no new addon, bridge, required dependency, security group or data
migration in this release.

### Notifications
- Removed the standalone Notifications item from the Workspace sidebar.
- Kept the same notification bell, unread counters, read actions, polling,
  permission filtering and combined EPS feed.
- Kept saved history accessible through Workspace history in the bell. Its page
  now says Notification history and explains that previously read updates remain.
- No notification data is deleted or marked read by this upgrade.

### Home cards
- The home dashboard now reuses the actual Accounting card markup and CSS classes:
  icon tile, upper-right arrow, rounded gradient surface, title, bottom Open
  workspace action, hover/focus and reduced-motion behavior.
- A card is one whole clickable anchor, not a list of submenus. Existing operational
  sidebar links remain. The destination is the existing role-filtered area URL.
- Four cards per large desktop row, two on smaller/tablet screens and one on narrow
  phones. Only authorized areas are rendered; no roles or permissions are granted.
- The existing Needs Your Attention component is unchanged.

### Switching between products
- With the existing bridge, a separate Go to / Employee Portal arrow control sits
  below the Workspace sidebar brand and ABOVE (not inside) the operational menu.
- EPS receives the matching Go to / Workspace arrow control in the same position.
- The old bridge-injected Business Workspaces list is replaced under the same
  inherited view XML id, rather than hidden or duplicated.
- The controls use the existing desktop sidebar/mobile drawer and normal anchors.
  Existing unsaved-change guards are not bypassed.
- Standalone Workspace users receive no unavailable Employee Portal link. EPS
  users without Workspace access receive no Workspace switch. Existing link
  authorization methods and default/login/deep-link routing are unchanged.
- The installed Employee Portal Suite source is not modified.

## Exact runtime changes
Main addon:
- __manifest__.py: version only.
- views/workspace_layout.xml: card markup, separate switch component, menu cleanup,
  history heading and scoped stylesheet reference.
- static/src/core/workspace_navigation.css: new scoped switch styles and home grid.

Existing EPS bridge:
- __manifest__.py: version only.
- views/navigation.xml: replaces its old menu injection with the separate switch
  and loads the shared stylesheet on EPS pages.

All other runtime files match the supplied input archives byte-for-byte. In
particular Sales/Purchase/Accounting/HR forms, controllers, models, security,
proposal editors, customer mapping, notification models/scripts, login routing,
the v0.9.8 percentage fix and v0.9.9 signatory removal are preserved.

## Verification performed
| Check | Result | Scope |
|---|---|---|
| Browser fixtures | 216 assertions passed | Actual shipped CSS/JS and QWeb-derived shell/card/switch markup at 1440, 1024, 768, 390 and 320px; standalone, integrated and restricted-role users; EPS integrated and EPS-only cases |
| Source/inheritance/preservation suite | 19 tests passed | Exact runtime diff, original EPS XPath targets, same XML ids, card component reuse, scoped assets, unchanged bell and proposal fixes |
| Retained layout suite | 10 tests passed | Original full-width structure, desktop scale, fonts and unrelated lists preserved; expected cache token adapted for the new CSS file |
| Retained notification suite | 41 tests passed | Existing notification methods with controlled ORM fixtures, role/company filters, read state, EPS combination and duplicate protection |

Browser checks cover responsive column count, no page-wide horizontal overflow,
keyboard/touch switch controls, mobile drawer opening/closing, correct link targets,
no cross-portal links mixed into operation lists, one visible bell, and history
remaining in the bell. Computed card height, corner radius, gradient, padding,
font family, shadow and gap match the existing Accounting card component.

## Test boundaries
This is NOT a live Odoo install/upgrade or a test on the user's server. Odoo and
its real registry/database are not present in this container. The browser fixture
uses a small local QWeb-like renderer, controlled users and mocked notification
responses, not the Odoo QWeb engine. Due to browser network policy it renders on
about:blank with a fixture-only origin adapter for link validation; the shipped
JavaScript was not modified. External fonts/logos were not loaded; icon/font/image
placeholders in local screenshots are fixture-only, not changes to the addon.
Real notification delivery, email, PDFs, taxes and end-to-end business workflows
were not rerun. Historical test reports included in the inputs remain historical.

An initial browser attempt was blocked by the environment's navigation policy;
the final local fixture suite completed. Fixture user data was completed with the
job title used by the original EPS profile. Python-generated __pycache__ files
were removed before final source comparisons and packaging.

## Upgrade
1. Replace the existing portal_backend_workspace folder with this complete folder.
2. Replace the existing portal_backend_workspace_eps_bridge folder where EPS is used.
3. Rebuild/restart as usual and upgrade portal_backend_workspace FIRST, then upgrade
   the SAME portal_backend_workspace_eps_bridge. Both versions are 18.0.0.9.10.
4. Refresh/reopen both portal pages. No uninstall or new addon is needed.

A Workspace-only installation uses the main ZIP only. Integrated installations
should upgrade both packages so the switch is moved on both sides. The default
landing-page rules are unchanged.

Implementation reference consulted: Odoo 18 QWeb templates and inheritance:
https://www.odoo.com/documentation/18.0/developer/reference/frontend/qweb.html
