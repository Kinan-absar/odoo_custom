/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.AuroraScrollAnimations = publicWidget.Widget.extend({
    selector: "#wrapwrap",

    start() {
        const result = this._super(...arguments);
        const targets = this.el.querySelectorAll(".o_aurora_animate");

        if (!targets.length) {
            return result;
        }

        const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        const isEditor = document.body.classList.contains("editor_enable");

        if (reduceMotion || isEditor || !("IntersectionObserver" in window)) {
            targets.forEach((element) => element.classList.add("o_aurora_animate_in"));
            return result;
        }

        this._observer = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("o_aurora_animate_in");
                    this._observer.unobserve(entry.target);
                }
            }
        }, { threshold: 0.15 });

        targets.forEach((element) => this._observer.observe(element));
        return result;
    },

    destroy() {
        this._observer?.disconnect();
        return this._super(...arguments);
    },
});
