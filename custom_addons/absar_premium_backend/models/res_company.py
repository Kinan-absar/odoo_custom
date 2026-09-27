from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Add the real font-family names to Odoo's native report font selector.
    # Odoo generates the company report SCSS from res.company.font, so using
    # the real family name is more reliable in wkhtmltopdf than an @font-face
    # alias based on local().
    font = fields.Selection(
        selection_add=[
            ("Noto Sans Arabic", "Noto Sans Arabic"),
            ("Tajawal", "Tajawal"),
            ("DejaVu Sans", "DejaVu Sans"),
            ("Tahoma", "Tahoma"),
            ("Arial", "Arial"),
            # Keep the legacy values temporarily so databases that tested the
            # previous build remain valid until Settings is saved once.
            ("ABSAR Arabic Noto", "Legacy ABSAR Noto (replace in ABSAR Theme)"),
            ("ABSAR Arabic Tajawal", "Legacy ABSAR Tajawal (replace in ABSAR Theme)"),
            ("ABSAR Arabic DejaVu", "Legacy ABSAR DejaVu (replace in ABSAR Theme)"),
        ],
        ondelete={
            "Noto Sans Arabic": "set default",
            "Tajawal": "set default",
            "DejaVu Sans": "set default",
            "Tahoma": "set default",
            "Arial": "set default",
            "ABSAR Arabic Noto": "set default",
            "ABSAR Arabic Tajawal": "set default",
            "ABSAR Arabic DejaVu": "set default",
        },
    )
