# -*- coding: utf-8 -*-

from odoo import fields, models, tools


class EmployeeMessageRecipient(models.Model):
    """Safe employee messaging directory for backend recipient search.

    This avoids granting broad access to hr.employee while still allowing
    internal users to search only employees linked to an Odoo user/partner.
    """
    _name = 'employee.message.recipient'
    _description = 'Employee Message Recipient'
    _auto = False
    _rec_name = 'name'
    _order = 'name'

    name = fields.Char(readonly=True)
    employee_id = fields.Many2one('hr.employee', readonly=True)
    user_id = fields.Many2one('res.users', readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)
    job_title = fields.Char(readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    is_portal_user = fields.Boolean(readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    e.id AS id,
                    e.id AS employee_id,
                    e.name AS name,
                    e.user_id AS user_id,
                    u.partner_id AS partner_id,
                    e.job_title AS job_title,
                    e.department_id AS department_id,
                    e.company_id AS company_id,
                    EXISTS (
                        SELECT 1
                          FROM res_groups_users_rel gur
                          JOIN res_groups g ON g.id = gur.gid
                          JOIN ir_model_data imd
                            ON imd.model = 'res.groups'
                           AND imd.res_id = g.id
                         WHERE gur.uid = u.id
                           AND imd.module = 'base'
                           AND imd.name = 'group_portal'
                    ) AS is_portal_user
                FROM hr_employee e
                JOIN res_users u ON u.id = e.user_id
                WHERE e.active = TRUE
                  AND e.user_id IS NOT NULL
                  AND u.partner_id IS NOT NULL
                  AND u.active = TRUE
            )
        """ % self._table)
