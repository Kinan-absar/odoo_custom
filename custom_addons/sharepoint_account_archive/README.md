# SharePoint Accounting Archive - Odoo 18

Archives posted Odoo accounting records to a SharePoint document library through Microsoft Graph.

## Archive structure

`<Root Folder>/<Year>/<MM - Month>/<Document Type>/<Odoo Number>/`

Each folder receives:
- an Odoo-generated PDF archive copy of the accounting move;
- binary attachments linked to the `account.move` (optional).

## Odoo setup

1. Copy `sharepoint_account_archive` to your Odoo.sh custom addons repository.
2. Commit and push.
3. Update Apps List and install **SharePoint Accounting Archive**.
4. Go to **Accounting > Configuration > SharePoint Archive**.
5. Create one configuration per company.
6. Enter Tenant ID, Client ID, Client Secret, SharePoint hostname, site path and document library name.
7. Click **Test & Resolve Connection**.

## Microsoft Entra / SharePoint setup

Recommended production permission: Microsoft Graph application permission `Sites.Selected`, with admin consent, then grant the application write access only to the intended SharePoint site.

For an initial controlled test you can temporarily use `Sites.ReadWrite.All`, then reduce permissions before production.

OAuth uses the client-credentials flow and `https://graph.microsoft.com/.default`.

## Notes

- Posting an entry does not wait for SharePoint. It marks the record Pending.
- The scheduled action runs every 5 minutes and handles up to 20 entries each run.
- Failed records are retried by the cron and can also be reset with the Retry SharePoint button.
- Simple upload is intentionally limited to 250 MB per file. Accounting attachments are normally far below this.
- Client secrets are stored in the Odoo database. Restrict access to System administrators and rotate the secret according to your security policy.
