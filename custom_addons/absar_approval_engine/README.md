# Absar Approval Engine — Odoo 18

A reusable technical application for configurable, multi-stage approvals.

## Included

- Workflows linked to any non-transient Odoo model
- Applicability domains and company-specific/global workflows
- Ordered approval stages
- Approvers from specific users, security groups, or a `res.users` field on the document
- Any-one, all, or minimum-count approval rules
- Approval and rejection comments
- Deadlines, overdue tracking, and activities
- Time-bounded approval delegation
- Requester self-approval policy
- Withdrawal, rejection, cancellation, and final approval hooks
- Immutable structured audit history
- Multi-company security
- Reusable abstract mixin

## Installation

1. Copy `absar_approval_engine` to your custom add-ons path.
2. Update the Apps list.
3. Install **Absar Approval Engine**.
4. Give users one of these groups:
   - Approval User
   - Approval Auditor
   - Approval Manager
5. Configure workflows under **Approvals → Configuration → Workflows**.

## Integrating a business model

Example for an existing custom model:

```python
from odoo import fields, models


class MaterialRequest(models.Model):
    _name = 'material.request'
    _inherit = ['material.request', 'absar.approval.engine.mixin']

    def action_submit(self):
        self.ensure_one()
        self.action_request_approval()
        self.state = 'waiting_approval'

    def _approval_engine_approved(self, request):
        self.write({'state': 'approved'})
        return super()._approval_engine_approved(request)

    def _approval_engine_rejected(self, request, reason):
        self.write({'state': 'rejected'})
        return super()._approval_engine_rejected(request, reason)
```

For a model already defined in the same module, use:

```python
class MaterialRequest(models.Model):
    _name = 'material.request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'absar.approval.engine.mixin']
```

Add buttons and status fields to its form:

```xml
<button name="action_request_approval" type="object" string="Submit for Approval"
        class="btn-primary"
        invisible="approval_state in ('draft', 'in_progress', 'approved')"/>
<button name="action_approval_approve" type="object" string="Approve"
        class="btn-primary" invisible="not approval_can_approve"/>
<button name="action_approval_reject" type="object" string="Reject"
        invisible="not approval_can_reject"/>
<field name="approval_state" widget="badge"/>
<field name="approval_stage_id"/>
```

Smart button:

```xml
<button name="action_open_approval_requests" type="object"
        class="oe_stat_button" icon="fa-check-square-o">
    <field name="approval_count" widget="statinfo" string="Approvals"/>
</button>
```

## Hooks

Override these methods in the business model:

- `_approval_engine_started(request)`
- `_approval_engine_approved(request)`
- `_approval_engine_rejected(request, reason)`

## Important integration rule

The target business model should include `mail.thread` and `mail.activity.mixin`. The engine mixin already inherits them, but explicit inheritance may still be useful for clarity in new models.
