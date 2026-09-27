/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

function hexToRgb(hex) {
    const value = (hex || "").trim().replace("#", "");
    if (!/^[0-9a-fA-F]{6}$/.test(value)) {
        return null;
    }
    return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16));
}

function darkenHex(hex, amount = 0.14) {
    const rgb = hexToRgb(hex);
    if (!rgb) return "";
    const out = rgb.map((v) => Math.max(0, Math.round(v * (1 - amount))));
    return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function applyTheme(config) {
    const root = document.documentElement;

    // Preserve the module's historical defaults unless explicitly disabled.
    root.classList.toggle("absar-rounded-buttons", config.rounded_buttons !== false);
    root.classList.toggle("absar-rounded-apps", config.rounded_apps !== false);

    const primary = (config.primary_color || "").trim();
    const hover = (config.primary_hover_color || "").trim() || darkenHex(primary);
    const rgb = hexToRgb(primary);

    root.classList.toggle("absar-custom-primary", Boolean(rgb));
    if (rgb) {
        root.style.setProperty("--absar-primary", primary);
        root.style.setProperty("--absar-primary-hover", hover || primary);
        root.style.setProperty("--absar-primary-rgb", rgb.join(", "));
    } else {
        root.style.removeProperty("--absar-primary");
        root.style.removeProperty("--absar-primary-hover");
        root.style.removeProperty("--absar-primary-rgb");
    }

    const font = config.backend_font_css || "";
    root.classList.toggle("absar-custom-font", Boolean(font));
    if (font) {
        root.style.setProperty("--absar-backend-font", font);
    } else {
        root.style.removeProperty("--absar-backend-font");
    }
}

function wireSettingsPreview() {
    const update = () => {
        for (const preview of document.querySelectorAll(".o_absar_theme_preview")) {
            const settings = preview.closest(".o_absar_theme_settings") || document;
            const primaryInput = settings.querySelector('input[name="absar_primary_color"]') || document.querySelector('input[name="absar_primary_color"]');
            const hoverInput = settings.querySelector('input[name="absar_primary_hover_color"]') || document.querySelector('input[name="absar_primary_hover_color"]');
            const primary = (primaryInput?.value || "").trim();
            const valid = hexToRgb(primary);
            if (valid) {
                preview.style.setProperty("--absar-preview-primary", primary);
                preview.style.setProperty("--absar-preview-hover", (hoverInput?.value || "").trim() || darkenHex(primary));
            } else {
                preview.style.removeProperty("--absar-preview-primary");
                preview.style.removeProperty("--absar-preview-hover");
            }
        }
    };
    document.addEventListener("input", (ev) => {
        if (ev.target?.matches?.('input[name="absar_primary_color"], input[name="absar_primary_hover_color"]')) {
            update();
        }
    }, true);
    document.addEventListener("change", update, true);
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    update();
}

const absarThemeService = {
    async start() {
        const root = document.documentElement;
        root.classList.add("absar-rounded-buttons", "absar-rounded-apps");
        wireSettingsPreview();
        try {
            const config = await rpc("/absar_premium_backend/theme_config", {});
            applyTheme(config || {});
        } catch (error) {
            console.warn("ABSAR theme settings could not be loaded.", error);
        }
    },
};

registry.category("services").add("absar_premium_backend.theme", absarThemeService);
