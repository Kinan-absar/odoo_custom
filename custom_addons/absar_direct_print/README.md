# Absar Direct Print — 18.0.1.0.9

The print dialog contains Report, Printer, and Copies. Office station is hidden and selected automatically. Canon is preselected when detected and enabled, unless you explicitly choose another default.

## Upgrade

Replace `custom_addons/absar_direct_print`, push, upgrade **Absar Direct Print**, and refresh Odoo. The Windows app and its existing pairing key remain unchanged.

## Choose which printers appear

Open **Settings → Direct Print → Office Stations** and open the station connected to your Windows app. Under **Printers on this computer**:

- Keep **Show in print dialog** checked for Canon and Epson.
- Untick it for Microsoft Print to PDF, OneNote, XPS, and any other printer you do not want offered.
- Set **Default printer** to **Canon MF440 Series** and save.

The Windows app manages detected names and availability. Refreshing discovery never resets your Show in print dialog choices. Only Direct Print Managers can change these settings.

The default follows your configured Default printer, then an enabled Canon printer, then the station's legacy default name, then the first enabled printer. Printing requires an enabled, detected printer from the selected station. A removed or disabled printer is rejected, even if an older open dialog still contains that selection.

## Automatic office computer

The print dialog uses your default station from user Preferences when permitted. Otherwise it uses the most recently connected permitted station, preferring the current company. Set your user default to the computer currently connected to the Windows app if an old station still exists. The station is retained internally to route jobs correctly and is hidden in the dialog.

One connected office computer can serve both Canon and Epson using one pairing key. Old stations and queued jobs are preserved; jobs are not moved or reprinted by this upgrade.

The printer icon placement, Settings menus, native Print buttons and existing invoice / Journal Voucher filtering are retained.

## Validation

Python compilation, XML, manifest/assets, ACLs and inherited Odoo 18 anchors checked. Seven existing Windows worker tests pass. Odoo tests for detection, defaults, visibility persistence, blocked destinations and access restrictions are included but could not be run without a live Odoo runtime. The Canon driver/queue issue needs a separate physical-printer test; this update changes selection and configuration.
