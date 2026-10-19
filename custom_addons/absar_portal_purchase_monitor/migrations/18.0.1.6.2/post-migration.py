def migrate(cr, version):
    # Review is mandatory for previously exempt working drafts too. Do not
    # reopen confirmed POs or change completed historical approvals.
    cr.execute("""UPDATE purchase_order SET absar_portal_preparer_id=COALESCE(absar_portal_preparer_id,create_uid),
        absar_portal_working_order=FALSE,state=CASE WHEN state='to approve' THEN 'draft' ELSE state END,absar_portal_review_state='draft',absar_portal_approver_id=NULL,
        absar_portal_approved_on=NULL WHERE absar_portal_working_order=TRUE AND state IN ('draft','sent','to approve')""")
