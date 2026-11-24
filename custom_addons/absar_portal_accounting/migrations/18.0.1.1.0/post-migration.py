def migrate(cr, version):
    for table in ('account_move','account_payment_voucher','account_receipt_voucher'):
        cr.execute('UPDATE "' + table + '" SET portal_accounting_review_required=TRUE WHERE portal_accounting_issuer_id IS NOT NULL')
