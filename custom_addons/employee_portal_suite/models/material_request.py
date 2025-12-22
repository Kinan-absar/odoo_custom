from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta
from odoo.exceptions import ValidationError

class MaterialRequest(models.Model):
    _name = 'material.request'
    _description = 'Material Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # ---------------------------------------------------------
    # BASIC FIELDS
    # ---------------------------------------------------------
    name = fields.Char(
        string='MR Number',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        tracking=True
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True
    )

    manager_id = fields.Many2one(
        'hr.employee',
        string='Direct Manager',
        compute="_compute_manager",
        store=True
    )

    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        tracking=True
    )

    worksite = fields.Char(string="Worksite", required=True)
    delivery_date = fields.Date(string="Delivery Date")

    line_ids = fields.One2many(
        'material.request.line',
        'request_id',
        string="Materials"
    )

    # ---------------------------------------------------------
    # STATE MACHINE
    # ---------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('purchase', 'Purchase Representative'),
        ('store', 'Store Manager'),
        ('project_manager', 'Project Manager'),
        ('director', 'Projects Director'),
        ('ceo', 'CEO Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)

    # Tracking who approved each stage
    purchase_approved_by = fields.Many2one("res.users", string="Purchase Approved By")
    store_approved_by = fields.Many2one("res.users", string="Store Manager Approved By")
    project_manager_approved_by = fields.Many2one("res.users", string="PM Approved By")
    director_approved_by = fields.Many2one("res.users", string="Director Approved By")
    ceo_approved_by = fields.Many2one("res.users", string="CEO Approved By")

    # ---------------------------------------------------------
    # APPROVAL METADATA (same pattern as employee.request)
    # ---------------------------------------------------------
    purchase_approved_by = fields.Many2one('res.users')
    purchase_approved_date = fields.Datetime()
    purchase_comment = fields.Text()

    store_approved_by = fields.Many2one('res.users')
    store_approved_date = fields.Datetime()
    store_comment = fields.Text()

    project_manager_approved_by = fields.Many2one('res.users')
    project_manager_approved_date = fields.Datetime()
    project_manager_comment = fields.Text()

    director_approved_by = fields.Many2one('res.users')
    director_approved_date = fields.Datetime()
    director_comment = fields.Text()

    ceo_approved_by = fields.Many2one('res.users')
    ceo_approved_date = fields.Datetime()
    ceo_comment = fields.Text()

    # Rejection info
    state_before_reject = fields.Char()
    rejected_by = fields.Many2one('res.users')

    # ---------------------------------------------------------
    # COMPUTE MANAGER
    # ---------------------------------------------------------
    @api.depends("employee_id")
    def _compute_manager(self):
        for rec in self:
            rec.manager_id = rec.employee_id.parent_id
    # ---------------------------------------------------------
    # DATE VALIDATION (Delivery Date must be 3+ days after Request Date)
    # ---------------------------------------------------------
    @api.onchange('request_date', 'delivery_date')
    def _onchange_delivery_date(self):
        if self.request_date and self.delivery_date:
            min_allowed = self.request_date + timedelta(days=3)
            if self.delivery_date < min_allowed:
                warning = {
                    'title': "Invalid Delivery Date",
                    'message': "Delivery Date must be at least 3 days after the Request Date."
                }
                # Reset delivery date so portal doesn't crash
                self.delivery_date = False
                return {'warning': warning}

    # ---------------------------------------------------------
    # CREATE SEQUENCE
    # ---------------------------------------------------------
    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code("material.request.seq") or _("New")
        return super().create(vals)

    # ---------------------------------------------------------
    # GENERIC STATE ADVANCE
    # ---------------------------------------------------------
    def _advance_state(self, new_state, group_xmlid, approved_user_field, approved_date_field):
        for rec in self:
            rec[approved_user_field] = self.env.user.id
            rec[approved_date_field] = fields.Datetime.now()

            rec.state = new_state
            rec.message_post(body=f"{new_state.capitalize()} stage approved.")
            rec.activity_ids.action_done()

            # Notify the next approval group
            group = self.env.ref(group_xmlid, raise_if_not_found=False)
            if group:
                for user in group.users:
                    rec._notify_user(
                        user,
                        f"Material Request {rec.name} requires your approval",
                        f"Material Request {rec.name} is waiting for your action."
                    )
                    rec._schedule_activity(
                        user,
                        "Approval Needed",
                        f"Please review Material Request {rec.name}."
                    )

    # ---------------------------------------------------------
    # NOTIFY / ACTIVITY HELPERS
    # ---------------------------------------------------------
    def _notify_user(self, user, subject, body):
        if not user or not user.partner_id.email:
            return
        mail_values = {
            "subject": subject,
            "body_html": f"<p>{body}</p>",
            "email_to": user.partner_id.email,
            "author_id": self.env.user.partner_id.id,
        }
        self.env["mail.mail"].sudo().create(mail_values).send()

    def _schedule_activity(self, user, summary, note):
        self.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=user.id,
            summary=summary,
            note=note
        )

    # ---------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------
    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError("Only draft requests can be submitted.")

            rec.state = "purchase"
            rec.message_post(body="Material Request submitted.")
            rec.activity_ids.action_done()

            # Notify Purchase Representative group
            group = self.env.ref("employee_portal_suite.group_mr_purchase_rep", raise_if_not_found=False)
            if group:
                for user in group.users:
                    rec._notify_user(
                        user,
                        "New Material Request Awaiting Approval",
                        f"Material Request {rec.name} requires your review."
                    )
                    rec._schedule_activity(
                        user,
                        "Purchase Approval Needed",
                        f"Material Request {rec.name} has been submitted."
                    )

    def action_purchase(self):
        self._advance_state(
            "store",
            "employee_portal_suite.group_mr_store_manager",
            "purchase_approved_by",
            "purchase_approved_date"
        )

    def action_store(self):
        self._advance_state(
            "project_manager",
            "employee_portal_suite.group_mr_project_manager",
            "store_approved_by",
            "store_approved_date"
        )

    def action_project_manager(self):
        self._advance_state(
            "director",
            "employee_portal_suite.group_mr_projects_director",
            "project_manager_approved_by",
            "project_manager_approved_date"
        )

    def action_director(self):
        self._advance_state(
            "ceo",
            "employee_portal_suite.group_employee_portal_ceo",
            "director_approved_by",
            "director_approved_date"
        )

    def action_ceo(self):
        for rec in self:
            if rec.state != "ceo":
                raise UserError("Request is not in CEO stage.")

            rec.ceo_approved_by = self.env.user.id
            rec.ceo_approved_date = fields.Datetime.now()
            rec.state = "approved"

            rec.message_post(body="Material Request fully approved.")
            rec.activity_ids.action_done()

            if rec.employee_id.user_id:
                rec._notify_user(
                    rec.employee_id.user_id,
                    "Material Request Approved",
                    f"Your Material Request {rec.name} has been approved."
                )

    def action_reject(self):
        for rec in self:
            if rec.state == "approved":
                raise UserError("Approved requests cannot be rejected.")

            rec.state_before_reject = rec.state
            rec.rejected_by = rec.env.user.id
            rec.state = "rejected"
            rec.message_post(body="Material Request rejected.")
            rec.activity_ids.action_done()

            if rec.employee_id.user_id:
                rec._notify_user(
                    rec.employee_id.user_id,
                    "Material Request Rejected",
                    f"Your Material Request {rec.name} has been rejected."
                )
    def get_rejection_reason(self):
        self.ensure_one()
        comments = {
            "purchase": self.purchase_comment,
            "store": self.store_comment,
            "project_manager": self.project_manager_comment,
            "director": self.director_comment,
            "ceo": self.ceo_comment,
        }
        return comments.get(self.state_before_reject) or ""

    # ---------------------------------------------------------
    # PORTAL TIMELINE
    # ---------------------------------------------------------
    def get_portal_timeline(self):
        self.ensure_one()
        timeline = []

        stages = [
            ("purchase", "Purchase Representative", self.purchase_approved_by, self.purchase_approved_date, self.purchase_comment),
            ("store", "Store Manager", self.store_approved_by, self.store_approved_date, self.store_comment),
            ("project_manager", "Project Manager", self.project_manager_approved_by, self.project_manager_approved_date, self.project_manager_comment),
            ("director", "Projects Director", self.director_approved_by, self.director_approved_date, self.director_comment),
            ("ceo", "CEO Approval", self.ceo_approved_by, self.ceo_approved_date, self.ceo_comment),
        ]

        for state, label, user, date, comment in stages:
            if date:
                timeline.append({
                    "stage": label,
                    "approved_by": user.name if user else "",
                    "date": date,
                    "comment": comment or "",
                })

        if self.state == "rejected":
            stage_labels = {
                "purchase": "Purchase Stage",
                "store": "Store Stage",
                "project_manager": "Project Manager Stage",
                "director": "Director Stage",
                "ceo": "CEO Stage",
            }

            comments = {
                "purchase": self.purchase_comment,
                "store": self.store_comment,
                "project_manager": self.project_manager_comment,
                "director": self.director_comment,
                "ceo": self.ceo_comment,
            }

            stage_label = stage_labels.get(self.state_before_reject, "Unknown Stage")
            comment = comments.get(self.state_before_reject) or "No comment"

            timeline.append({
                "stage": f"{stage_label} - Rejected",
                "approved_by": self.rejected_by.name if self.rejected_by else "",
                "date": self.write_date,
                "comment": comment,
            })

        return timeline
        
    def get_readable_status(self):
        mapping = {
            "purchase": "Pending Purchase",
            "store": "Pending Store Manager",
            "project_manager": "Pending PM",
            "director": "Pending Director",
            "ceo": "Pending CEO",
            "approved": "Fully Approved",
            "rejected": "Rejected",
        }
        return mapping.get(self.state, "Unknown")


    #Purchase Extension 
    def action_create_po(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Order",
            "res_model": "purchase.order",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_material_request_id": self.id,
            },
        }

    # LINK TO PURCHASE ORDERS (required)
    purchase_order_ids = fields.One2many(
        "purchase.order",
        "material_request_id",
        string="Purchase Orders",
    )

    # SHOW PO NUMBER(S) IN LIST VIEW
    po_name = fields.Char(
        string="Purchase Order",
        compute="_compute_po_name",
        store=False,
    )
    po_status = fields.Char(
        string="PO Status",
        compute="_compute_po_status",
        store=False,
    )

    # ❗❗ INSERTED HERE — BUTTON VISIBILITY BOOLEAN ❗❗
    can_create_po = fields.Boolean(
        compute="_compute_can_create_po",
        store=False,
    )

    def _compute_can_create_po(self):
        for rec in self:
            rec.can_create_po = (
                rec.state == "approved"
                and not rec.purchase_order_ids
            )

    # END OF INSERTION

    def _compute_po_name(self):
        for rec in self:
            if len(rec.purchase_order_ids) == 1:
                rec.po_name = rec.purchase_order_ids.name
            elif len(rec.purchase_order_ids) > 1:
                rec.po_name = ", ".join(rec.purchase_order_ids.mapped("name"))
            else:
                rec.po_name = ""
                #status badge
    def _compute_po_status(self):
        for rec in self:

            # Always assign something (avoid crash)
            if not rec.purchase_order_ids:
                rec.po_status = False
                continue

            po = rec.purchase_order_ids[0]  # Usually only 1 PO

            mapping = {
                "draft": "RFQ",
                "sent": "RFQ Sent",
                "to approve": "Waiting Approval",
                "purchase": "Purchase Order",
                "done": "Received",
                "cancel": "Cancelled",
            }

            rec.po_status = mapping.get(po.state, po.state)

    def action_open_po(self):
        self.ensure_one()

        if not self.purchase_order_ids:
            return

        # If exactly one PO → open directly in form view
        if len(self.purchase_order_ids) == 1:
            po = self.purchase_order_ids[0]
            return {
                "type": "ir.actions.act_window",
                "name": "Purchase Order",
                "res_model": "purchase.order",
                "res_id": po.id,
                "view_mode": "form",
                "target": "current",
            }

        # If multiple POs → open list + form views
        return {
            "type": "ir.actions.act_window",
            "name": "Purchase Orders",
            "res_model": "purchase.order",
            "domain": [("id", "in", self.purchase_order_ids.ids)],
            "view_mode": "list,form",
            "target": "current",
        }

        
from odoo import models, api

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for att in records:
            if att.res_model == 'material.request':
                att.public = True
        return records
