# ABSAR Premium Backend 18.0.5.2.0

Configurable backend theme for Odoo 18.

## Settings
Go to **Settings -> ABSAR Theme**.

- Primary color + hover/pressed color
- Link color + hover/pressed color
- Backend UI font (expanded list)
- Rounded buttons on/off
- Rounded app icons on/off
- PDF / report font using Odoo's native company report-font mechanism

For Arabic PDFs, try **Tajawal** first, then **Noto Sans Arabic**.  The report CSS
forces nested company/contact address text to inherit the selected layout font,
including mixed lines such as `42317 المدينة المنورة`.
