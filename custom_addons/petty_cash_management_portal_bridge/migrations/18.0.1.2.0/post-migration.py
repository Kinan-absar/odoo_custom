def migrate(cr, version):
    # Older portal uploads were created with public=True. Make existing petty cash
    # report/line attachments private now that the portal uses a secured download route.
    cr.execute("""
        UPDATE ir_attachment
           SET public = FALSE
         WHERE public = TRUE
           AND res_model IN ('petty.cash', 'petty.cash.line')
    """)
