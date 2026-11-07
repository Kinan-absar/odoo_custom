def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO hr_employee_multi_work_location_rel (employee_id, work_location_id)
        SELECT id, work_location_id
          FROM hr_employee
         WHERE work_location_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
