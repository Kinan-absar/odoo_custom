from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env=api.Environment(cr,SUPERUSER_ID,{})
    group=env.ref('absar_portal_sales.group_portal_sales_user')
    cr.execute("""UPDATE sale_order SET absar_portal_creator_id=create_uid,
        absar_portal_review_state='draft',absar_portal_approver_id=NULL
        WHERE absar_portal_creator_id IS NULL AND state IN ('draft','sent')
        AND create_uid IN (SELECT uid FROM res_groups_users_rel WHERE gid=%s)""",[group.id])
