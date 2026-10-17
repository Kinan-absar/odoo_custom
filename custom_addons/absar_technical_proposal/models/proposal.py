from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare

SECTION_TYPES = [
    ('executive', 'Executive Summary'),
    ('quantity', 'Quantity Takeoff Summary'),
    ('technical', 'Technical Specifications & Engineering Framework'),
    ('quality', 'Quality Assurance & Testing'),
    ('commercial', 'Commercial Terms / Exclusions'),
    ('legal', 'Legal & Contractual Clauses'),
    ('schedule', 'Execution Schedule'),
    ('confirmation', 'Proposal Confirmation & Next Steps'),
    ('custom', 'Custom Section'),
]

CONFIRMATION_DEFAULT = """<p>We appreciate the opportunity to submit our Technical &amp; Financial Proposal for your consideration.</p>
<p>Should our proposal meet your technical and commercial requirements, kindly confirm your acceptance by issuing an official Purchase Order or written confirmation referencing this proposal, including the agreed scope of work, contract value, and payment terms.</p>
<p>Upon receipt of your confirmation and fulfillment of the agreed commercial conditions, ABSAR Al Omran Company will coordinate the necessary arrangements to commence the works.</p>
<p>We look forward to your favorable response and the opportunity to work together.</p>"""


class ProposalTemplate(models.Model):
    _name = 'absar.proposal.template'
    _description = 'Technical Proposal Template'
    _order = 'name'
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    title = fields.Char(default='TECHNICAL & FINANCIAL PROPOSAL')
    section_ids = fields.One2many('absar.proposal.template.section', 'template_id', string='Sections', copy=True)
    payment_ids = fields.One2many('absar.proposal.template.payment', 'template_id', string='Payment Schedule', copy=True)

class ProposalTemplateSection(models.Model):
    _name = 'absar.proposal.template.section'
    _description = 'Proposal Template Section'
    _order = 'sequence, id'
    template_id = fields.Many2one('absar.proposal.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    section_type = fields.Selection(SECTION_TYPES, required=True, default='custom')
    name = fields.Char(required=True)
    content = fields.Html(sanitize=True)
    include_in_report = fields.Boolean(default=True)
    page_break_before = fields.Boolean()

    @api.onchange('section_type')
    def _onchange_section_type_name(self):
        if not self.name or self.name in dict(SECTION_TYPES).values():
            self.name = dict(SECTION_TYPES).get(self.section_type, '')
        if self.section_type == 'confirmation' and not self.content:
            self.content = CONFIRMATION_DEFAULT

class ProposalTemplatePayment(models.Model):
    _name = 'absar.proposal.template.payment'
    _description = 'Proposal Template Payment Milestone'
    _order = 'sequence, id'
    template_id = fields.Many2one('absar.proposal.template', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    percentage = fields.Float(required=True, digits=(16, 2))
    due_condition = fields.Char()
    @api.constrains('percentage')
    def _check_percentage(self):
        for rec in self:
            if rec.percentage < 0 or rec.percentage > 100:
                raise ValidationError(_('Milestone percentage must be between 0 and 100.'))

class ProposalSection(models.Model):
    _name = 'absar.proposal.section'
    _description = 'Quotation Technical Proposal Section'
    _order = 'sequence, id'
    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    sequence = fields.Integer(default=10)
    section_type = fields.Selection(SECTION_TYPES, required=True, default='custom')
    name = fields.Char(required=True)
    content = fields.Html(sanitize=True)
    include_in_report = fields.Boolean(default=True)
    page_break_before = fields.Boolean()

    @api.onchange('section_type')
    def _onchange_section_type_name(self):
        if not self.name or self.name in dict(SECTION_TYPES).values():
            self.name = dict(SECTION_TYPES).get(self.section_type, '')
        if self.section_type == 'confirmation' and not self.content:
            self.content = CONFIRMATION_DEFAULT

class ProposalPayment(models.Model):
    _name = 'absar.proposal.payment'
    _description = 'Quotation Proposal Payment Milestone'
    _order = 'sequence, id'
    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    percentage = fields.Float(required=True, digits=(16, 2))
    due_condition = fields.Char()
    amount = fields.Monetary(compute='_compute_amount', currency_field='currency_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    @api.depends('percentage', 'order_id.amount_untaxed')
    def _compute_amount(self):
        for line in self:
            line.amount = line.order_id.amount_untaxed * line.percentage / 100
    @api.constrains('percentage')
    def _check_percentage(self):
        for rec in self:
            if rec.percentage < 0 or rec.percentage > 100:
                raise ValidationError(_('Milestone percentage must be between 0 and 100.'))

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    absar_proposal_type = fields.Selection([('standard', 'Standard Quotation'), ('technical', 'Technical & Financial Proposal')], default='standard', required=True, copy=True, tracking=True, string='Document Type')
    absar_proposal_title = fields.Char(default='TECHNICAL & FINANCIAL PROPOSAL', copy=True)
    absar_proposal_reference = fields.Char(string='External Proposal Reference', copy=True)
    absar_proposal_template_id = fields.Many2one('absar.proposal.template', string='Proposal Template', check_company=True)
    absar_proposal_section_ids = fields.One2many('absar.proposal.section', 'order_id', copy=True, string='Proposal Sections')
    absar_proposal_payment_ids = fields.One2many('absar.proposal.payment', 'order_id', copy=True, string='Payment Milestones')
    absar_proposal_signatory = fields.Char(string='ABSAR Authorized Signatory')
    absar_proposal_signatory_title = fields.Char(string='ABSAR Signatory Title')
    absar_proposal_customer_signatory = fields.Char(string='Customer Authorized Signatory')
    absar_proposal_customer_signatory_title = fields.Char(string='Customer Signatory Title')

    def action_absar_load_proposal_template(self):
        self.ensure_one()
        if self.state not in ('draft', 'sent'):
            raise UserError(_('Proposal templates can only be applied to draft or sent quotations.'))
        template = self.absar_proposal_template_id
        if not template:
            raise UserError(_('Select a proposal template first.'))
        sections = [(0, 0, {
            'sequence': s.sequence, 'section_type': s.section_type, 'name': s.name,
            'content': s.content, 'include_in_report': s.include_in_report,
            'page_break_before': s.page_break_before,
        }) for s in template.section_ids]
        if not any(s.section_type == 'confirmation' for s in template.section_ids):
            sections.append((0, 0, {
                'sequence': 999, 'section_type': 'confirmation',
                'name': 'Proposal Confirmation & Next Steps',
                'content': CONFIRMATION_DEFAULT, 'include_in_report': True,
            }))
        self.write({
            'absar_proposal_type': 'technical',
            'absar_proposal_title': template.title,
            'absar_proposal_section_ids': [(5, 0, 0)] + sections,
            'absar_proposal_payment_ids': [(5, 0, 0)] + [(0, 0, {
                'sequence': p.sequence, 'name': p.name, 'percentage': p.percentage,
                'due_condition': p.due_condition,
            }) for p in template.payment_ids],
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_absar_print_technical_proposal(self):
        self.ensure_one()
        if self.absar_proposal_type != 'technical':
            raise UserError(_('Choose Technical & Financial Proposal as the document type first.'))
        if self.absar_proposal_payment_ids:
            total = sum(self.absar_proposal_payment_ids.mapped('percentage'))
            if float_compare(total, 100.0, precision_digits=2) != 0:
                raise UserError(_('Payment milestones must total 100%% before printing (currently %.2f%%).') % total)
        return self.env.ref('absar_technical_proposal.action_report_absar_technical_proposal').report_action(self)
