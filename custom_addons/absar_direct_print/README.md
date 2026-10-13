# Absar Direct Print — 18.0.1.0.8

One office Windows computer can now use multiple printers through one station and one pairing key. The existing Windows app is compatible; no app update is needed.

## Upgrade and connect Canon + Epson

1. Replace the existing `custom_addons/absar_direct_print` folder with this version. Push and upgrade **Absar Direct Print**, then refresh Odoo.
2. Keep the station currently connected to your Windows app (the Canon station in your screenshot). In **Settings → Direct Print → Office Stations**, you can rename it **Office Computer**. Keep its existing pairing key in the app; do not renew it just for this update.
3. Leave the app running. It reports all printers installed on the computer, and Odoo automatically updates **Printers on this computer**. Refresh the station form after a few seconds; Canon and Epson should be listed if Windows detects both.
4. Open a document's printer icon. Select **Office Computer** under **Office station**, then select **Canon MF440 Series** or **EPSONC66C03 (L14150 Series)** under **Printer**, choose copies, and click **Print**.
5. Set **Office Computer** as your default station in user Preferences if desired.

The old Epson station is no longer needed for new print jobs. Existing jobs remain tied to their original station; this update does not move, cancel, or reprint them. Review any queued Epson jobs before retiring that station.

## Printer selection

- Each station represents one Windows computer. Each detected printer belongs to that station.
- **Default Windows printer** on the station remains an optional default. The print dialog preselects that printer when detected, or the only detected printer if exactly one exists.
- Selecting another printer overrides the default for that job. Leaving Printer empty uses the station default, then the app's local default, then Windows default.
- Printers missing from the app's latest report are hidden from new selections. Submitting a saved selection for a removed printer or a different station is rejected.
- Printer names come from Windows and cannot be created or edited by ordinary Odoo users. Existing company and allowed-user restrictions continue to apply.

If Epson is not listed, verify it is installed and can print from the Windows account running the app. A disconnected or sleeping PC cannot receive jobs. **Active** on an Odoo station is an administrative setting, not a live connection indicator; check **Last Seen**.

The existing printer icon placement, Settings menus, invoice/Journal Voucher report filtering, and native Print buttons are retained.

## Job status

Queued means waiting for the app. Processing means claimed. Sent to Windows confirms submission to the print system, not physical paper output. For Failed, inspect Message and the Windows printer queue. For Needs review, check whether paper already printed before retrying.

PDF limit: 25 MB. Copies: 1–20. PDF snapshots expire after 7 days; history after 30 days. The app uses outbound HTTPS and an encrypted pairing key; it does not require an Odoo password or a paid cloud printing subscription.

## Validation

Python compilation, XML/assets/access definitions and Odoo 18 inherited-template anchors were checked. Seven tests passed against the unchanged Windows worker, including sequential routing to Canon and Epson using the same station key. Odoo TransactionCase tests for discovery, defaults, station/company restrictions and printer removal are included; a live Odoo runtime and physical printers were unavailable for local execution. Upgrade and verify one copy on each printer in your environment.
