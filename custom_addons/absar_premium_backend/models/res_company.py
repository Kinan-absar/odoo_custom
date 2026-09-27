from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Composite report-font choices.  Each family is defined in report assets
    # with separate Unicode ranges so Arabic glyphs use the selected Arabic font
    # while Latin text keeps Lato.  This avoids odd Latin glyphs (notably "o")
    # when an Arabic-oriented font is selected for a bilingual report.
    font = fields.Selection(
        selection_add=[
            ("ABSAR Arabic Noto", "ABSAR Arabic - Noto Sans Arabic (Latin stays Lato)"),
            ("ABSAR Arabic Tajawal", "ABSAR Arabic - Tajawal (Latin stays Lato)"),
            ("ABSAR Arabic DejaVu", "ABSAR Arabic - DejaVu Sans (Latin stays Lato)"),
        ],
        ondelete={
            "ABSAR Arabic Noto": "set default",
            "ABSAR Arabic Tajawal": "set default",
            "ABSAR Arabic DejaVu": "set default",
        },
    )
