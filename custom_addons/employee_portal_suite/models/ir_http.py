from odoo import models
from odoo.http import request
from werkzeug.exceptions import Forbidden


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _auth_method_absar_internal(cls):
        cls._auth_method_user()
        if not request.env.user._is_internal():
            raise Forbidden()
