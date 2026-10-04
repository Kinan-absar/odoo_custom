# Absar Direct Print — Odoo 18

Version 18.0.1.0.0. Independent add-on; does not modify Employee Portal Suite or Construction.

## Install on staging

1. Put `absar_direct_print` in your repository's `custom_addons`, push, and wait for the staging build.
2. Update the Apps list and install **Absar Direct Print**.
3. The administrator receives Direct Print Manager access. Give other internal users **Direct Print User** in Settings → Users → Access Rights.
4. In your user Preferences enable **Show print options**. Refresh the browser after installation.
5. Use an existing report from Odoo's Print menu. The new dialog offers **Browser Print**, **Print to Office**, and **Download PDF**.

## Browser test — no Windows app needed

Select Browser Print. Allow the report tab to open. It renders Odoo's HTML report and requests the browser print dialog after images and fonts load. If the browser suppresses automatic printing, press the report's Print button. Select your local printer and confirm.

HTML print layout can differ from the PDF, especially headers, footers and page counters. Check the browser preview first. The office option uses the original generated PDF. Reports exposed only through a custom direct-download URL, Excel exports, and portal print links are outside the initial integration. Standard backend `ir.actions.report` PDF actions are intercepted, including custom reports using that standard action.

## Office test

1. Direct Print → Office Stations → New. Name it `Office Windows` and choose its company.
2. If multiple printers exist, enter the exact Windows printer name. Empty uses the default selected locally in the app, then the Windows default.
3. Save. Click **Pair / Renew Key**. Copy the Odoo HTTPS address and key into the Windows app.
4. Restrict Allowed users if needed. Empty allows all Direct Print users with access to that company.
5. Select the station in your Preferences as your default, or choose it in each print dialog.
6. Start the app on Windows; the station's Last seen should update within a few seconds.
7. Print one test report with one copy. Confirm paper output before trying real documents.

## Queue behavior

Queued: waiting for the app. Processing: claimed by that station. Sent to Windows: PDF print command succeeded and the job was handed to the print system; NOT physical delivery confirmation. Failed: print command or input validation failed. Needs review: app interruption, lost receipt, or timeout; check the printer before a manager retries.

A claimed job is marked Needs review after 10 minutes when the station next polls. It is never automatically requeued. Local durable receipts prevent automatic repeated submission after restart. A manager's explicit Retry permits another attempt and can create another paper copy. Pending jobs are cancelled from Print Jobs. Jobs already processing cannot reliably be cancelled here; use the Windows printer queue.

Unsubmitted PDF data expires after 7 days. History expires after 30 days. Expired jobs need a new report generation. Maximum PDF size 25 MB; 1–20 copies.

## Security and connections

Report rendering runs with the sender's Odoo permissions. Jobs are scoped to station and company; ordinary users see their own jobs. The desktop uses a revocable station key, not an Odoo user password. Pairing keys are stored encrypted with Windows DPAPI for the current Windows account. Treat a key like a password: anyone holding it can retrieve PDFs queued to that station.

Only outbound HTTPS from Windows to Odoo is used. No router port forwarding, inbound listening service or separate paid printing relay. Pair staging separately; pairing keys do not need to be reused on production. Remove or revoke test stations before a database is cloned or exposed to a different environment. Existing queued PDFs are snapshots; access revoked later does not remove an already queued document—cancel that job explicitly.

## Validation

Python compile checks, XML/manifest/reference checks, and six worker unit tests pass. Odoo TransactionCase tests are included for staging/test environments: station restrictions, job ACLs, cross-company boundaries, and wizard ownership. They have not been executed in a live Odoo server here. Windows setup, DPAPI, and physical printing require a Windows staging test; they have not been executed on your computer.

To run Odoo tests in a dedicated disposable database: enable tests and use tag `/absar_direct_print`. Do not use a production database for installation tests.

## Uninstall / disable

Turn off Show print options to restore normal report behavior per user. Stop the desktop app to stop receiving new work. Revoke a station key to disconnect it. Remove the add-on through Odoo before removing its source folder. Do not delete the source of an installed module first.
