/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

/**
 * Aurora Theme — scroll fade-in animation.
 * Any element with class `o_aurora_animate` fades/slides into view once it
 * enters the viewport. Uses IntersectionObserver so it's cheap and doesn't
 * run on every scroll event.
 */
publicWidget.registry.AuroraScrollAnimations = publicWidget.Widget.extend({
    selector: "#wrapwrap",

    start() {
        this._super(...arguments);

        const targets = this.el.querySelectorAll(".o_aurora_animate");
        if (!targets.length) {
            return Promise.resolve();
        }

        if (!("IntersectionObserver" in window)) {
            // Fallback: just show everything immediately.
            targets.forEach((el) => el.classList.add("o_aurora_animate_in"));
            return Promise.resolve();
        }

        this._observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("o_aurora_animate_in");
                        this._observer.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.15 }
        );

        targets.forEach((el) => this._observer.observe(el));

        return Promise.resolve();
    },

    destroy() {
        if (this._observer) {
            this._observer.disconnect();
        }
        this._super(...arguments);
    },
});

export default publicWidget.registry.AuroraScrollAnimations;
