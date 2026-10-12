# 18.0.2.47.0 — Conversion cleanup and selected CEO submission

## Convert to Payable
When conversion merges into an existing supplier-balance Planned Payment, the replaced PO plan is now deleted rather than cancelled. Its name and ID are retained in the recommendation reason, and Target Payable Plan identifies the retained record. Existing CEO/execution eligibility checks remain. A source linked to a voucher or internal transfer cannot be deleted automatically. Unlink follows normal user access and database transaction rules; failures roll back the conversion.

When there is no existing payable plan, the source is converted in place: no replaced duplicate exists to delete. Remove recommendations still cancel. Already-cancelled records from previous conversions are not automatically purged by this upgrade; select the obsolete records in Planned Payments and use Actions / Delete after checking them.

## Planned Payments list
Select multiple records, then click Submit to CEO in the list header. The server validates the entire selection first. Only planned outgoing payments with CEO Decision Not Sent and a supplier are accepted. Receipts, cancelled/executed/awaiting-payment items, unplanned actuals, and previously submitted/reviewed payments cause an explicit error with no submission. Successful selection uses the existing submission workflow, marks each Pending, and refreshes the same list.

The previous 18.0.2.46.0 navigation and checkbox fixes are included.

## Validation
38 offline regression checks passed, including two sequential conversions reusing one payable target and deleting the replaced source, preservation of voucher-linked sources, multi-record CEO submission, and rejection of mixed/invalid selections before mutations. Python syntax, 26 XML files, and ZIP integrity checked. These changes have not yet been installed or browser-tested on staging.
