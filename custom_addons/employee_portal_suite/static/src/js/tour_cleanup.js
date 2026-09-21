/** @odoo-module **/

const removeOldEmployeeTours = () => {
    try {
        localStorage.removeItem("eps_demo_manager_tour");
        localStorage.removeItem("eps_demo_portal_tour_step");
        localStorage.removeItem("eps_demo_portal_tour_open");
    } catch (_) {}

    document.getElementById("eps-demo-portal-tour-widget")?.remove();
    document.querySelectorAll(".eps-portal-tour-highlight,.eps_demo_tour_highlight").forEach((el) => {
        el.classList.remove("eps-portal-tour-highlight", "eps_demo_tour_highlight");
    });

    document.querySelectorAll("button").forEach((btn) => {
        if ((btn.textContent || "").trim() === "Guided Setup Tour") {
            btn.remove();
        }
    });
    document.querySelectorAll(".card").forEach((card) => {
        if ((card.textContent || "").includes("MANAGER SETUP TOUR")) {
            card.remove();
        }
    });
};

removeOldEmployeeTours();
const observer = new MutationObserver(removeOldEmployeeTours);
observer.observe(document.documentElement, { childList: true, subtree: true });
