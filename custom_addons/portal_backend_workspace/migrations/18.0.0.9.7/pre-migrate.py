"""Restore the original customer schema without rewriting existing flags."""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""SELECT column_name FROM information_schema.columns
                  WHERE table_schema=current_schema() AND table_name='res_partner'
                  AND column_name IN ('absar_is_sales_customer', 'pbw_is_sales_customer')""")
    columns = {row[0] for row in cr.fetchall()}
    if 'absar_is_sales_customer' in columns:
        _logger.info('PBW: original Customer / Client column exists; values preserved unchanged.')
        return
    cr.execute('ALTER TABLE res_partner ADD COLUMN absar_is_sales_customer boolean')
    if 'pbw_is_sales_customer' in columns:
        cr.execute('UPDATE res_partner SET absar_is_sales_customer=COALESCE(pbw_is_sales_customer, FALSE)')
    _logger.info('PBW: restored Customer / Client column from standalone workspace data.')
