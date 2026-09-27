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
    if (!rgb) {
        return "";
    }
    const out = rgb.map((v) => Math.max(0, Math.round(v * (1 - amount))));
    return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function setBooleanClass(root, enabled, onClass, offClass) {
    root.classList.toggle(onClass, Boolean(enabled));
    if (offClass) {
        root.classList.remove(offClass);
    }
}

function applyTheme(config) {
    const root = document.documentElement;

    setBooleanClass(root, config.rounded_buttons !== false, "absar-rounded-buttons", "absar-square-buttons");
    setBooleanClass(root, config.rounded_apps !== false, "absar-rounded-apps", "absar-square-apps");

    const primary = (config.primary_color || "").trim();
    const primaryRgb = hexToRgb(primary);
    const primaryHover = (config.primary_hover_color || "").trim() || darkenHex(primary);

    root.classList.toggle("absar-custom-primary", Boolean(primaryRgb));
    if (primaryRgb) {
        root.style.setProperty("--absar-primary", primary);
        root.style.setProperty("--absar-primary-hover", primaryHover || primary);
        root.style.setProperty("--absar-primary-rgb", primaryRgb.join(", "));
    } else {
        root.style.removeProperty("--absar-primary");
        root.style.removeProperty("--absar-primary-hover");
        root.style.removeProperty("--absar-primary-rgb");
    }

    const link = (config.link_color || "").trim();
    const linkRgb = hexToRgb(link);
    const linkHover = (config.link_hover_color || "").trim() || darkenHex(link);
    root.classList.toggle("absar-custom-link", Boolean(linkRgb));
    if (linkRgb) {
        root.style.setProperty("--absar-link", link);
        root.style.setProperty("--absar-link-hover", linkHover || link);
        root.style.setProperty("--absar-link-rgb", linkRgb.join(", "));
    } else {
        root.style.removeProperty("--absar-link");
        root.style.removeProperty("--absar-link-hover");
        root.style.removeProperty("--absar-link-rgb");
    }

    const font = config.backend_font_css || "";
    root.classList.toggle("absar-custom-font", Boolean(font));
    if (font) {
        root.style.setProperty("--absar-backend-font", font);
    } else {
        root.style.removeProperty("--absar-backend-font");
    }
}

function fieldInput(settings, fieldName) {
    return settings.querySelector(`input[name="${fieldName}"]`) ||
        settings.querySelector(`.o_field_widget[name="${fieldName}"] input`);
}

function syncColorPickers(container = document) {
    container.querySelectorAll("input.o_absar_color_picker[data-absar-target]").forEach((picker) => {
        const settings = picker.closest(".o_absar_theme_settings") || document;
        const fieldName = picker.dataset.absarTarget;
        const textInput = fieldInput(settings, fieldName) || fieldInput(document, fieldName);
        if (!textInput) {
            return;
        }
        const value = (textInput.value || "").trim();
        if (hexToRgb(value) && picker.value.toLowerCase() !== value.toLowerCase()) {
            picker.value = value;
        }
    });
}

function updatePreview() {
    document.querySelectorAll(".o_absar_theme_preview").forEach((preview) => {
        const settings = preview.closest(".o_absar_theme_settings") || document;
        const primaryInput = fieldInput(settings, "absar_primary_color") || fieldInput(document, "absar_primary_color");
        const primaryHoverInput = fieldInput(settings, "absar_primary_hover_color") || fieldInput(document, "absar_primary_hover_color");
        const linkInput = fieldInput(settings, "absar_link_color") || fieldInput(document, "absar_link_color");
        const linkHoverInput = fieldInput(settings, "absar_link_hover_color") || fieldInput(document, "absar_link_hover_color");

        const primary = (primaryInput?.value || "").trim();
        if (hexToRgb(primary)) {
            preview.style.setProperty("--absar-preview-primary", primary);
            preview.style.setProperty(
                "--absar-preview-primary-hover",
                (primaryHoverInput?.value || "").trim() || darkenHex(primary)
            );
        } else {
            preview.style.removeProperty("--absar-preview-primary");
            preview.style.removeProperty("--absar-preview-primary-hover");
        }

        const link = (linkInput?.value || "").trim();
        if (hexToRgb(link)) {
            preview.style.setProperty("--absar-preview-link", link);
            preview.style.setProperty(
                "--absar-preview-link-hover",
                (linkHoverInput?.value || "").trim() || darkenHex(link)
            );
        } else {
            preview.style.removeProperty("--absar-preview-link");
            preview.style.removeProperty("--absar-preview-link-hover");
        }
    });
    syncColorPickers();
}

function applyLiveToggleFromSettings(target) {
    if (!target?.matches?.('input[type="checkbox"]')) {
        return;
    }
    const root = document.documentElement;
    const widget = target.closest(".o_field_widget");
    const name = target.name || widget?.getAttribute("name");
    if (name === "absar_rounded_buttons") {
        setBooleanClass(root, target.checked, "absar-rounded-buttons", "absar-square-buttons");
    }
    if (name === "absar_rounded_apps") {
        setBooleanClass(root, target.checked, "absar-rounded-apps", "absar-square-apps");
    }
}

const absarThemeService = {
    async start() {
        document.addEventListener("input", (ev) => {
            const picker = ev.target?.closest?.("input.o_absar_color_picker[data-absar-target]");
            if (picker) {
                const fieldName = picker.dataset.absarTarget;
                const settings = picker.closest(".o_absar_theme_settings") || document;
                const textInput = fieldInput(settings, fieldName) || fieldInput(document, fieldName);
                if (textInput && textInput.value !== picker.value) {
                    textInput.value = picker.value.toUpperCase();
                    textInput.dispatchEvent(new Event("input", { bubbles: true }));
                    textInput.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
            updatePreview();
            applyLiveToggleFromSettings(ev.target);
        }, true);
        document.addEventListener("change", (ev) => {
            updatePreview();
            applyLiveToggleFromSettings(ev.target);
        }, true);
        setTimeout(updatePreview, 0);

        try {
            const config = await rpc("/absar_premium_backend/theme_config", {});
            applyTheme(config || {});
        } catch (error) {
            console.warn("ABSAR theme settings could not be loaded.", error);
        }
    },
};

registry.category("services").add("absar_premium_backend.theme", absarThemeService);
