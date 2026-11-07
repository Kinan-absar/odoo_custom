from werkzeug.exceptions import Forbidden
from odoo import http
from odoo.http import request


class PortalBackendWorkspace(http.Controller):
    """A standalone portal shell. Business controllers are NOT migrated yet."""

    _sections = (
        ('sales', 'Sales', 'Quotations, orders and approvals', 'fa-line-chart'),
        ('purchase', 'Purchase', 'Orders, receiving and vendor reviews', 'fa-shopping-cart'),
        ('accounting', 'Accounting', 'Bills, customer invoices and entries', 'fa-calculator'),
        ('hr', 'HR Administration', 'Employees, contracts and attendance', 'fa-users'),
    )

    def _allowed_sections(self):
        user = request.env.user
        if user._is_public() or not user.has_group('portal_backend_workspace.group_workspace_user'):
            raise Forbidden()
        return [dict(key=key, title=title, description=description, icon=icon)
                for key, title, description, icon in self._sections
                if user.has_group('portal_backend_workspace.group_workspace_' + key)]

    @http.route('/my/workspace', type='http', auth='user', website=True, methods=['GET'])
    def dashboard(self, **kwargs):
        sections = self._allowed_sections()
        return request.render('portal_backend_workspace.workspace_dashboard', {
            'sections': sections,
            'active_section': 'home',
            'company_name': request.env.company.name,
        })

    @http.route('/my/workspace/<string:section>', type='http', auth='user', website=True, methods=['GET'])
    def section(self, section, **kwargs):
        sections = self._allowed_sections()
        selected = next((item for item in sections if item['key'] == section), None)
        if not selected:
            raise Forbidden()
        return request.render('portal_backend_workspace.workspace_section', {
            'sections': sections,
            'active_section': section,
            'section': selected,
            'company_name': request.env.company.name,
        })
