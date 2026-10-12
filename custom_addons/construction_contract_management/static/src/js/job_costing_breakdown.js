/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const SECTION_META = [
    { key: "vendor_bills", label: "Vendor Bills", hint: "Expense accounts" },
    { key: "customer_invoices", label: "Customer Invoices", hint: "Revenue accounts" },
    { key: "credit_notes", label: "Credit Notes", hint: "Revenue accounts" },
    { key: "overhead", label: "Overhead", hint: "Expense accounts" },
];

export class JobCostingBreakdown extends Component {
    static template = "construction_contract_management.JobCostingBreakdown";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.state = useState({ expanded: Object.fromEntries(SECTION_META.map((section) => [section.key, false])) });
    }

    get payload() {
        try {
            const value = this.props.record.data[this.props.name];
            return value ? JSON.parse(value) : {};
        } catch {
            return {};
        }
    }

    get sections() {
        const data = this.payload;
        return SECTION_META.map((section) => {
            const rows = (data.groups || {})[section.key] || [];
            const amountKey = {
                vendor_bills: "vendor_total",
                customer_invoices: "invoice_total",
                credit_notes: "credit_note_total",
                overhead: "overhead_total",
            }[section.key];
            return { ...section, rows, total: data[amountKey] || 0 };
        });
    }

    formatAmount(amount) {
        const number = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount || 0);
        return `${number} ${this.payload.currency || ""}`.trim();
    }

    toggleSection(key) {
        this.state.expanded[key] = !this.state.expanded[key];
    }

    async printReport() {
        const id = this.props.record.resId || this.props.record.data.id;
        if (!id) {
            return;
        }
        await this.action.doAction("construction_contract_management.action_report_job_costing", {
            additionalContext: {
                active_model: "construction.contract",
                active_id: id,
                active_ids: [id],
                job_costing_expanded: JSON.stringify(this.state.expanded),
            },
        });
    }
}

registry.category("fields").add("ccm_job_costing_breakdown", {
    component: JobCostingBreakdown,
    supportedTypes: ["text"],
});
