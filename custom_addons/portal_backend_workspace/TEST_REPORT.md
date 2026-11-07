# Portal Backend Workspace 18.0.0.9.4 - notification release

## Scope
Changes apply to the standalone base addon and the optional EPS bridge. The base
starts from v0.9.3 including its menu removal and original-layout fixes. The bridge
starts from v0.9. The four business workspaces are not replaced or redesigned.

## Implemented
- A persistent, permission-filtered workspace notification bell, desktop and mobile.
- Existing Sales, Purchase and Accounting approval/outcome emitters feed the bell.
- HR gateway actions and native contract/payslip/payroll-batch status changes notify
  other authorized HR/payroll administrators. No new HR approval workflow is added.
  Bulk payroll generation emits one batch update instead of a notice per child save.
- Optional bridge reads the original EPS summary and replaces its existing bell with
  the same component. It does not copy EPS events or maintain a second EPS inbox.
- Per-user read state, individual read controls, workspace history and mark-workspace-
  updates-read. Reading a notification neither approves a document nor clears pending
  approval counters. EPS notifications retain the original EPS read/visit behavior.
- Automatic refresh every 20 seconds while the page is visible, plus refresh on focus
  or opening the bell. Tabs share only refresh signals, not notification contents.
- Current company, role, ownership, journal and target-record access are checked before
  displaying or opening notices. CSRF-protected acknowledgements apply only to the
  signed-in user's eligible records. No generic portal ORM read grant is introduced.
- One persisted row per recipient/event; bell totals do not add the same workspace
  approval queue to its individual event count. A read watermark preserves events
  arriving after the displayed snapshot.
- EPS's existing Calls/Messages mounting and MR message submit guard are preserved by
  the bridge without changing the EPS addon or restoring its competing bell poller.

## Executed checks
| Check | Result | What it establishes |
| --- | --- | --- |
| Offline Python notification/security tests | 41 passed | Actual shipped methods with controlled ORM fixtures; scope, recipients, event deduplication, foreign read denial, revocation, HR events, EPS integration, install guard |
| Browser fixture assertions | 84 passed | Shipped bell markup/CSS/JavaScript in Chromium; standalone/integrated/EPS-only at 1440/390px, one visible bell, read controls, counts, automatic refresh, cross-portal refresh, safe content, EPS compatibility |
| Retained layout contract checks | 10 passed | Previously repaired shell layout contract remains |
| Retained targeted parity checks | 21 passed | Previously repaired narrow features remain |
| Python/XML/JavaScript/manifest/bridge inheritance checks | Passed | Source parses, declared files exist and inherited template targets match supplied source |
| Business source preservation | Passed | Sales/Purchase/Accounting business models/controllers/views/assets unchanged; HR views/assets unchanged; existing global layout CSS and Settings-menu removal unchanged |

The browser checks use local HTML and mocked HTTP endpoints, not the user's website.
The opaque about:blank fixture has a test-only URL-origin adapter; shipped URL checks
are unchanged. The browser suite checks real 20-second refresh timing. Mocked checks
are not a substitute for Odoo registry, database, permission-rule or network tests.

## Not executed / not claimed
A live Odoo installation/upgrade and delivery between real Odoo user sessions were
not executed in this environment. Seven optional real-registry tests are supplied
under tests/ with tag pbw_notifications, but were not run. The complete historical
workflow suite and feature parity with every original addon were not revalidated;
prior limitations remain documented in PARITY_AUDIT.md and historical test reports.
This release adds in-app notifications; it does not implement browser/OS push or
email delivery when the portal is closed. Existing EPS push behavior is untouched.
Historical business actions with no saved PBW event are not reconstructed. Existing
persisted events remain available only if the user still has document access.

## Upgrade
Replace the complete base addon folder and upgrade portal_backend_workspace first.
For EPS integration, replace and upgrade portal_backend_workspace_eps_bridge next.
Do not uninstall either product. Refresh open browser tabs after upgrading. Existing
user groups and company/journal restrictions remain; the actor is not notified about
its own action. Use a second correctly authorized user for a delivery test.

## Recommended live acceptance checks
1. In PBW alone, submit a quotation/PO/bill from one preparer and open a different,
   company-authorized approver's bell. Approve or return and check the preparer's bell.
2. With the bridge, compare unread contents on /my/employee and /my/workspace for a
   dual-access user. Mark a PBW notice read in one and verify the other refreshes.
3. Verify EPS-only users see only EPS notifications; PBW-only users have no unauthorized
   document data. Revoke a workspace/journal permission and repeat the feed request.
4. Make an HR/payroll operation with one administrator and check another permitted
   administrator. Employee-only HR access must not expose payroll notifications.
5. Confirm that reading an alert does not approve its document and that Calls/Messages
   and MR message submission still behave normally within EPS.
