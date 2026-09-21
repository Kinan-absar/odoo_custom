/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY = "ccm_demo_tour_v1";

const STEPS = [
    { title: "Construction Contracts", body: "Welcome. This tour follows the complete construction commercial cycle: Contract → BOQ → Measurement → IPC → Invoice/Bill → Variations → Advance → Retention.", action: "construction_contract_management.action_construction_dashboard", target: ".o_form_view, .ccm_dashboard" },
    { title: "Dashboard", body: "Start from the commercial dashboard. It summarizes active contracts and pending IPCs, variations, advances and retention releases, with shortcuts for daily work.", action: "construction_contract_management.action_construction_dashboard", target: ".ccm_dashboard, .o_form_view" },
    { title: "Contracts", body: "A Contract is the master record. It can represent a client contract or subcontract and connects the Project, Partner, dates, commercial terms and the full downstream workflow.", action: "construction_contract_management.action_construction_contract", target: ".o_list_view" },
    { title: "Create / Open a Contract", body: "Open a contract or click New. Set the Project, Partner and Contract Direction. Contract Direction determines whether the commercial flow is client-side or subcontractor-side.", action: "construction_contract_management.action_construction_contract", target: ".o_list_button_add, button.o_list_button_add" },
    { title: "Commercial Terms", body: "Inside the Contract Details tab, define Original Amount, Retention %, Advance %, payment terms, scope and notes. Revised Amount updates as approved variations affect the contract.", action: "construction_contract_management.action_construction_contract", target: "[name='original_amount'], [name='retention_percent'], [name='advance_percent']" },
    { title: "BOQ", body: "The BOQ is maintained directly on the contract. Add item codes, descriptions, units, contract quantities and rates. Measurements and IPCs will follow these BOQ lines.", action: "construction_contract_management.action_construction_contract", target: "[name='boq_line_ids']" },
    { title: "Measurements", body: "Measurements record actual progress against the BOQ. Choose a Contract, load its BOQ lines, enter current quantities, then Submit → Check → Approve.", action: "construction_contract_management.action_construction_measurement", target: ".o_list_view" },
    { title: "Measurement Approval", body: "Only approved measurements should feed certification. The workflow provides Draft, Submitted, Checked, Approved and Rejected stages with BOQ quantity control.", action: "construction_contract_management.action_construction_measurement", target: ".o_statusbar_status, .o_list_view" },
    { title: "IPCs / Payment Certificates", body: "Create an IPC for the Contract and select an approved Measurement. Load the measurement to bring the certified BOQ quantities into the payment certificate.", action: "construction_contract_management.action_construction_ipc", target: ".o_list_view" },
    { title: "IPC Amounts", body: "The IPC calculates current work value and applies Advance Recovery and Retention. After approval, create the accounting Invoice/Bill or link an existing accounting document.", action: "construction_contract_management.action_construction_ipc", target: ".o_list_view, [name='current_work_value']" },
    { title: "Variations", body: "Use Variations for approved changes to contract scope, quantity or rate. Approved variations update the contract/BOQ revised values while preserving the original contract baseline.", action: "construction_contract_management.action_construction_variation", target: ".o_list_view" },
    { title: "Advances", body: "Advances are tracked separately by Contract. Record the advance amount and VAT/accounting setup, then create the related Invoice/Bill. IPCs can recover the advance progressively.", action: "construction_contract_management.action_construction_advance", target: ".o_list_view" },
    { title: "Retention Releases", body: "Retention withheld through IPCs remains tracked against the Contract. When it becomes due, create a Retention Release and post it using the required accounting method.", action: "construction_contract_management.action_construction_retention_release", target: ".o_list_view" },
    { title: "Complete Workflow", body: "You have now seen the full flow. Use the smart buttons on a Contract to move between its Measurements, IPCs, Variations, Advances and Retention Releases. You can now explore the demo freely.", action: "construction_contract_management.action_construction_contract", target: ".o_list_view" },
];

export class ConstructionDemoTour extends Component {
    static template = "construction_contract_management.ConstructionDemoTour";
    setup() {
        this.action = useService("action");
        this.state = useState({ open: false, step: 0 });
        this._timer = null;
        onMounted(() => {
            const saved = window.sessionStorage.getItem(STORAGE_KEY);
            if (saved) {
                try { const s = JSON.parse(saved); this.state.open = !!s.open; this.state.step = Math.min(Number(s.step) || 0, STEPS.length - 1); } catch (_) {}
            }
            if (this.state.open) this._scheduleHighlight();
        });
        onWillUnmount(() => { if (this._timer) clearTimeout(this._timer); this._clearHighlight(); });
    }
    get stepData() { return STEPS[this.state.step]; }
    get stepNumber() { return this.state.step + 1; }
    get totalSteps() { return STEPS.length; }
    get progress() { return `${Math.round((this.stepNumber / this.totalSteps) * 100)}%`; }
    toggle() { this.state.open = !this.state.open; this._save(); if (this.state.open) this._scheduleHighlight(); else this._clearHighlight(); }
    close() { this.state.open = false; this._save(); this._clearHighlight(); }
    async start() { this.state.open = true; this.state.step = 0; this._save(); await this._openCurrent(); }
    async next() { if (this.state.step < STEPS.length - 1) { this.state.step++; this._save(); await this._openCurrent(); } }
    async previous() { if (this.state.step > 0) { this.state.step--; this._save(); await this._openCurrent(); } }
    async openStep() { await this._openCurrent(); }
    _save() { window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({open: this.state.open, step: this.state.step})); }
    async _openCurrent() {
        this._clearHighlight();
        const step = this.stepData;
        if (step.action) {
            try { await this.action.doAction(step.action); } catch (e) { console.warn("CCM demo tour action failed", e); }
        }
        this._scheduleHighlight();
    }
    _scheduleHighlight() { if (this._timer) clearTimeout(this._timer); this._timer = setTimeout(() => this._highlight(), 650); }
    _clearHighlight() { document.querySelectorAll(".ccm_tour_target").forEach((el) => el.classList.remove("ccm_tour_target")); }
    _highlight() {
        this._clearHighlight();
        const selectors = (this.stepData.target || "").split(",").map(s => s.trim()).filter(Boolean);
        for (const selector of selectors) {
            const el = document.querySelector(selector);
            if (el) { el.classList.add("ccm_tour_target"); el.scrollIntoView({behavior:"smooth", block:"center"}); break; }
        }
    }
}

registry.category("main_components").add("construction_contract_demo_tour", { Component: ConstructionDemoTour });
