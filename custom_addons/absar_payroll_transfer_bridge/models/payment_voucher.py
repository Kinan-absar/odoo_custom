from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountPaymentVoucher(models.Model):
    _inherit = "account.payment.voucher"

    # Payroll Transfer has no single partner. The employee partners live on the
    # generated accrued-salary debit lines instead.
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
        required=False,
    )

    payment_method = fields.Selection(
        selection_add=[("payroll_transfer", "Payroll Transfer")],
        ondelete={"payroll_transfer": "set default"},
    )

    payroll_run_id = fields.Many2one(
        "hr.payslip.run",
        string="Payroll Batch",
        copy=False,
        check_company=True,
        help=(
            "Payroll batch to settle. The bridge reads the posted accrued-salary "
            "journal lines created for this batch and automatically creates one "
            "debit line per employee partner."
        ),
    )

    payroll_source_move_ids = fields.Many2many(
        "account.move",
        string="Payroll Journal Entries",
        compute="_compute_payroll_transfer_info",
        readonly=True,
    )

    payroll_employee_count = fields.Integer(
        string="Employees",
        compute="_compute_payroll_transfer_info",
        readonly=True,
    )

    payroll_outstanding_amount = fields.Monetary(
        string="Payroll Amount",
        compute="_compute_payroll_transfer_info",
        currency_field="currency_id",
        readonly=True,
    )

    @api.depends(
        "payment_method",
        "payroll_run_id",
        "company_id",
        "company_id.payroll_accrued_salary_account_id",
    )
    def _compute_payroll_transfer_info(self):
        for rec in self:
            rec.payroll_source_move_ids = False
            rec.payroll_employee_count = 0
            rec.payroll_outstanding_amount = 0.0
            if rec.payment_method != "payroll_transfer" or not rec.payroll_run_id:
                continue

            info = rec._get_payroll_transfer_source_info(raise_on_error=False)
            rec.payroll_source_move_ids = info["moves"]
            rec.payroll_employee_count = len(info["partner_amounts"])
            rec.payroll_outstanding_amount = sum(info["partner_amounts"].values())

    def _get_payroll_batch_slips(self):
        self.ensure_one()
        if not self.payroll_run_id:
            return self.env["hr.payslip"]
        return self.env["hr.payslip"].search([
            ("payslip_run_id", "=", self.payroll_run_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "!=", "cancel"),
        ])

    def _get_payroll_transfer_source_info(self, raise_on_error=True):
        """Return the exact accounting source for the selected payroll batch.

        The bridge deliberately reads the already-generated payroll journal entry
        instead of recalculating salary rules. That guarantees that the transfer
        matches the amount actually posted to the configured accrued salary account.
        """
        self.ensure_one()
        empty = {
            "account": self.env["account.account"],
            "slips": self.env["hr.payslip"],
            "moves": self.env["account.move"],
            "source_lines": self.env["account.move.line"],
            "partner_lines": {},
            "partner_amounts": {},
        }

        if not self.payroll_run_id or not self.company_id:
            return empty

        account = self.company_id.payroll_accrued_salary_account_id
        if not account:
            if raise_on_error:
                raise UserError(_(
                    "Please configure the Employee Accrued Salary account first in "
                    "Payroll > Configuration > Settings."
                ))
            return empty

        slips = self._get_payroll_batch_slips()
        if not slips:
            if raise_on_error:
                raise UserError(_("The selected payroll batch has no payslips."))
            return {**empty, "account": account}

        missing_moves = slips.filtered(lambda slip: not slip.move_id)
        if missing_moves:
            if raise_on_error:
                raise UserError(_(
                    "Some payslips in payroll batch '%s' do not have an accounting entry yet. "
                    "Complete the payroll batch before creating the transfer."
                ) % self.payroll_run_id.display_name)
            slips = slips - missing_moves

        moves = slips.mapped("move_id")
        unposted_moves = moves.filtered(lambda move: move.state != "posted")
        if unposted_moves:
            if raise_on_error:
                raise UserError(_(
                    "All payroll journal entries must be posted before the Payroll Transfer can be posted. "
                    "Draft entries: %s"
                ) % ", ".join(unposted_moves.mapped("display_name")))
            moves = moves.filtered(lambda move: move.state == "posted")

        source_lines = moves.mapped("line_ids").filtered(
            lambda line: line.account_id == account
            and line.partner_id
            and line.balance < 0
        )

        partner_lines = defaultdict(lambda: self.env["account.move.line"])
        partner_amounts = defaultdict(float)
        currency = self.company_id.currency_id

        for line in source_lines:
            if account.reconcile:
                # Credit liability lines carry a negative residual balance.
                amount = max(-line.amount_residual, 0.0)
            else:
                amount = max(-line.balance, 0.0)
            amount = currency.round(amount)
            if currency.is_zero(amount):
                continue
            partner_lines[line.partner_id.id] |= line
            partner_amounts[line.partner_id.id] += amount

        partner_amounts = {
            partner_id: currency.round(amount)
            for partner_id, amount in partner_amounts.items()
            if not currency.is_zero(amount)
        }
        partner_lines = {
            partner_id: lines
            for partner_id, lines in partner_lines.items()
            if partner_id in partner_amounts
        }

        return {
            "account": account,
            "slips": slips,
            "moves": moves,
            "source_lines": source_lines,
            "partner_lines": partner_lines,
            "partner_amounts": partner_amounts,
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Persist the payroll amount even though it is readonly in the form.

        Odoo does not always send onchange-only values for readonly fields when a
        new voucher is saved. Since ``amount`` is mandatory on the base Payment
        Voucher model, a Payroll Transfer could fail to save/post even though the
        amount was visibly computed on screen. Recompute it server-side before
        creation so the accounting record never depends on browser behavior.
        """
        prepared_vals_list = []
        for incoming in vals_list:
            vals = dict(incoming)
            if (
                vals.get("payment_method") == "payroll_transfer"
                and vals.get("payroll_run_id")
                and not vals.get("amount")
            ):
                company = self.env["res.company"].browse(
                    vals.get("company_id") or self.env.company.id
                )
                run = self.env["hr.payslip.run"].browse(vals["payroll_run_id"])
                account = company.payroll_accrued_salary_account_id
                if account and run.exists():
                    slips = self.env["hr.payslip"].search([
                        ("payslip_run_id", "=", run.id),
                        ("company_id", "=", company.id),
                        ("state", "!=", "cancel"),
                    ])
                    moves = slips.mapped("move_id").filtered(lambda move: move.state == "posted")
                    lines = moves.mapped("line_ids").filtered(
                        lambda line: line.account_id == account
                        and line.partner_id
                        and line.balance < 0
                    )
                    total = 0.0
                    for line in lines:
                        if account.reconcile:
                            total += max(-line.amount_residual, 0.0)
                        else:
                            total += max(-line.balance, 0.0)
                    total = company.currency_id.round(total)
                    if not company.currency_id.is_zero(total):
                        vals["amount"] = total
                    vals.setdefault("account_id", account.id)
            prepared_vals_list.append(vals)
        return super().create(prepared_vals_list)

    @api.onchange("payment_method")
    def _onchange_absar_payroll_transfer_method(self):
        if self.payment_method == "payroll_transfer":
            self.partner_id = False
            self.purchase_order_id = False
            self.purchase_order_ids = [(5, 0, 0)]
            self.po_allocation_ids = [(5, 0, 0)]
            self.bill_ids = [(5, 0, 0)]
            self.line_ids = [(5, 0, 0)]
            self.has_bank_fees = False
            self.fee_amount = 0.0
            self.fee_account_id = False
            self.fee_tax_id = False
            self.analytic_distribution = False
            self.account_id = self.company_id.payroll_accrued_salary_account_id
        else:
            self.payroll_run_id = False

    @api.onchange("payroll_run_id", "company_id")
    def _onchange_payroll_run_id(self):
        if self.payment_method != "payroll_transfer":
            return
        self.account_id = self.company_id.payroll_accrued_salary_account_id
        if not self.payroll_run_id:
            self.amount = 0.0
            return
        info = self._get_payroll_transfer_source_info(raise_on_error=False)
        total = sum(info["partner_amounts"].values())
        self.amount = self.currency_id.round(total)
        if self.payroll_run_id.name:
            self.description = _("Payroll Transfer - %s") % self.payroll_run_id.name

    @api.constrains("payment_method", "partner_id", "payroll_run_id", "company_id")
    def _check_payroll_transfer_requirements(self):
        for rec in self:
            if rec.payment_method == "payroll_transfer":
                if not rec.payroll_run_id:
                    raise ValidationError(_("Please select a Payroll Batch."))
                run_company = getattr(rec.payroll_run_id, "company_id", False)
                if run_company and run_company != rec.company_id:
                    raise ValidationError(_("The payroll batch and voucher must belong to the same company."))
            elif not rec.partner_id:
                raise ValidationError(_("Please select a Partner."))

    def _check_duplicate_payroll_transfer(self):
        self.ensure_one()
        duplicate = self.search([
            ("id", "!=", self.id),
            ("payment_method", "=", "payroll_transfer"),
            ("payroll_run_id", "=", self.payroll_run_id.id),
            ("company_id", "=", self.company_id.id),
            ("state", "!=", "cancel"),
        ], limit=1)
        if duplicate:
            raise UserError(_(
                "Payroll batch '%(batch)s' is already linked to Payment Voucher %(voucher)s. "
                "Cancel that voucher first if you need to recreate the payroll transfer."
            ) % {
                "batch": self.payroll_run_id.display_name,
                "voucher": duplicate.display_name,
            })

    def _post_payroll_transfer(self):
        self.ensure_one()
        rec = self

        if rec.state != "draft":
            return True
        if not rec.journal_id or not rec.journal_id.default_account_id:
            raise UserError(_("Please select a source Bank/Cash journal with a default account."))
        if rec.currency_id != rec.company_id.currency_id:
            raise UserError(_(
                "Payroll Transfer currently uses the company currency because the source payroll journal "
                "is posted in company currency. Please use %s."
            ) % rec.company_id.currency_id.display_name)

        rec._check_duplicate_payroll_transfer()
        info = rec._get_payroll_transfer_source_info(raise_on_error=True)
        account = info["account"]
        partner_amounts = info["partner_amounts"]
        if not partner_amounts:
            raise UserError(_(
                "No outstanding employee accrued-salary credit lines were found for payroll batch '%s'."
            ) % rec.payroll_run_id.display_name)

        total = rec.currency_id.round(sum(partner_amounts.values()))
        if rec.currency_id.is_zero(total):
            raise UserError(_("The selected payroll batch has no amount left to pay."))

        # The payroll journal is the accounting source of truth. Keep the voucher
        # amount/account synchronized with it so users never type 40-100 allocations.
        rec.write({
            "amount": total,
            "account_id": account.id,
            "partner_id": False,
            "purchase_order_ids": [(5, 0, 0)],
            "bill_ids": [(5, 0, 0)],
        })

        label = rec.payroll_run_id.name or rec.description or rec.name
        move_lines = []
        for partner_id, amount in sorted(partner_amounts.items()):
            move_lines.append((0, 0, {
                "account_id": account.id,
                "partner_id": partner_id,
                "debit": amount,
                "credit": 0.0,
                "name": label,
            }))

        # One bank/cash credit for the complete payroll transfer.
        move_lines.append((0, 0, {
            "account_id": rec.journal_id.default_account_id.id,
            "partner_id": False,
            "debit": 0.0,
            "credit": total,
            "name": label,
        }))

        move_vals = {
            "date": rec.date,
            "journal_id": rec.journal_id.id,
            "ref": rec.description or label or rec.name,
            "line_ids": [(5, 0, 0)] + move_lines,
        }

        if rec.move_id:
            if rec.move_id.state != "draft":
                raise UserError(_(
                    "This Payroll Transfer is already linked to journal entry %s which is not in draft. "
                    "Reset the voucher to draft before reposting."
                ) % rec.move_id.display_name)
            rec.move_id.with_context(check_move_validity=False).write(move_vals)
            move = rec.move_id
        else:
            move = self.env["account.move"].create(move_vals)
            rec.move_id = move.id

        move.action_post()

        # Reconcile employee by employee when the accrued salary account allows it.
        # The statement still works without reconciliation, but reconciliation makes
        # the outstanding balance and duplicate-payment protection much stronger.
        if account.reconcile:
            payment_lines_by_partner = {
                line.partner_id.id: line
                for line in move.line_ids.filtered(
                    lambda line: line.account_id == account and line.partner_id and line.debit > 0
                )
            }
            for partner_id, source_lines in info["partner_lines"].items():
                payment_line = payment_lines_by_partner.get(partner_id)
                if payment_line:
                    (source_lines | payment_line).reconcile()

        rec.state = "posted"
        rec.message_post(body=_(
            "Payroll Transfer posted for batch <b>%(batch)s</b>: %(employees)s employees, total %(amount)s."
        ) % {
            "batch": rec.payroll_run_id.display_name,
            "employees": len(partner_amounts),
            "amount": rec.currency_id.format(total),
        })
        return True

    def action_post(self):
        payroll_records = self.filtered(lambda rec: rec.payment_method == "payroll_transfer")
        normal_records = self - payroll_records

        result = True
        if normal_records:
            result = super(AccountPaymentVoucher, normal_records).action_post()
            # Parent may return an overpayment confirmation action.
            if isinstance(result, dict):
                return result

        for rec in payroll_records:
            rec._post_payroll_transfer()
        return result

    def action_reset_to_draft(self):
        payroll_records = self.filtered(lambda rec: rec.payment_method == "payroll_transfer")
        normal_records = self - payroll_records

        if normal_records:
            super(AccountPaymentVoucher, normal_records).action_reset_to_draft()

        for rec in payroll_records:
            if rec.state not in ("posted", "cancel"):
                continue
            if rec.move_id:
                accrued_account = rec.company_id.payroll_accrued_salary_account_id
                if accrued_account:
                    payment_lines = rec.move_id.line_ids.filtered(
                        lambda line: line.account_id == accrued_account and line.partner_id
                    )
                    if payment_lines:
                        payment_lines.remove_move_reconcile()
                if rec.move_id.state == "posted":
                    # No tax lines exist on Payroll Transfer entries, so the normal
                    # draft transition is safe and keeps Odoo's move integrity checks.
                    rec.move_id.button_draft()
            super(AccountPaymentVoucher, rec.with_context(skip_cash_plan_link_lock=True)).write({"state": "draft"})
        return True
