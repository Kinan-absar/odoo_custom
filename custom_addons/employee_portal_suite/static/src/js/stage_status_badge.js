/** @odoo-module **/
import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
export class StageStatusBadge extends Component {
    static props = { ...standardFieldProps };
    static template = xml`<span t-att-class="badgeClass" t-att-title="label"><t t-esc="label"/></span>`;
    get label() { return this.props.record.data[this.props.name] || ""; }
    get badgeClass() {
        const data = this.props.record.data;
        const color = this.props.name === "display_state" && data.needs_clarification
            ? 13 : Number(data.approval_status_color) || 0;
        return `badge rounded-pill eps-stage-status eps-stage-color-${color}`;
    }
}
registry.category("fields").add("eps_stage_status_badge", {
    component: StageStatusBadge,
    supportedTypes: ["char"],
});
