/** @odoo-module **/

// PWA shell for the existing native Odoo Discuss experience.
// No chat, attachment, voice-note, presence or RTC logic is duplicated here.
// Those remain entirely owned by Odoo Discuss.

(() => {

function enforceEmployeePortalFavicon() {
    const head = document.head;
    if (!head) return;
    // Odoo's web.layout ships its own favicon. Safari can keep choosing that
    // first icon even when a later PNG is present, so remove competing favicons
    // only on the Employee Portal surface and install one stable, cache-busted set.
    head.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((link) => {
        if (link.dataset.employeePortalIcon !== "1") link.remove();
    });
    head.querySelectorAll('link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]').forEach((link) => {
        if (link.dataset.employeePortalTouchIcon !== "1") link.remove();
    });
    const touchIcons = [
        ["apple-touch-icon", "", "/employee_portal_suite/static/icons/apple-touch-icon.png?v=45"],
        ["apple-touch-icon", "180x180", "/employee_portal_suite/static/icons/portal-180.png?v=45"],
        ["apple-touch-icon-precomposed", "", "/employee_portal_suite/static/icons/apple-touch-icon-precomposed.png?v=45"],
    ];
    for (const [rel, sizes, href] of touchIcons) {
        const link = document.createElement("link");
        link.rel = rel;
        if (sizes) link.sizes = sizes;
        link.href = href;
        link.dataset.employeePortalTouchIcon = "1";
        head.appendChild(link);
    }
    const icons = [
        ["shortcut icon", "image/x-icon", "", "/employee_portal_suite/static/icons/portal-favicon-v45.ico?v=45"],
        ["icon", "image/png", "16x16", "/employee_portal_suite/static/icons/portal-16.png?v=45"],
        ["icon", "image/png", "32x32", "/employee_portal_suite/static/icons/portal-32.png?v=45"],
        ["icon", "image/png", "64x64", "/employee_portal_suite/static/icons/portal-64.png?v=45"],
    ];
    for (const [rel, type, sizes, href] of icons) {
        const link = document.createElement("link");
        link.rel = rel;
        link.type = type;
        if (sizes) link.sizes = sizes;
        link.href = href;
        link.dataset.employeePortalIcon = "1";
        head.appendChild(link);
    }
}

    const APP_ROOT = "/my/employee/discuss";
    const PORTAL_ROOT = "/my/employee";
    const normalizedPath = () => window.location.pathname.replace(/\/+$/, "") || "/";
    const isDiscussSurface = () => normalizedPath().startsWith(APP_ROOT);
    const isCanonicalHome = () => normalizedPath() === APP_ROOT;
    if (!isDiscussSurface()) return;
    enforceEmployeePortalFavicon();

    let deferredInstallPrompt = null;
    let titleObserver = null;

    function ensureMeta(name, content) {
        let meta = document.querySelector(`meta[name="${name}"][data-employee-discuss-pwa]`)
            || document.querySelector(`meta[name="${name}"]`);
        if (!meta) {
            meta = document.createElement("meta");
            meta.name = name;
            document.head.appendChild(meta);
        }
        meta.content = content;
        meta.dataset.employeeDiscussPwa = "1";
        return meta;
    }

    function addHeadMetadata() {
        if (!document.querySelector('link[rel="manifest"][data-employee-discuss-pwa]')) {
            const link = document.createElement("link");
            link.rel = "manifest";
            link.href = `${PORTAL_ROOT}/manifest.webmanifest`;
            link.dataset.employeeDiscussPwa = "1";
            document.head.appendChild(link);
        }
        ensureMeta("theme-color", "#ffffff");
        ensureMeta("apple-mobile-web-app-capable", "yes");
        ensureMeta("apple-mobile-web-app-title", "ABSAR Employee");
        ensureMeta("application-name", "ABSAR Employee");
    }

    // Safari's Add to Dock uses the current document URL/title more heavily than
    // Chromium's manifest-driven install flow. The neutral Discuss home must
    // therefore keep a stable "Chats" identity even though Odoo bootstraps the
    // native Discuss store from a real conversation behind the scenes.
    function enforceCanonicalHomeIdentity() {
        if (!isCanonicalHome()) return;
        if (document.title !== "Chats") {
            document.title = "Chats";
        }
        ensureMeta("apple-mobile-web-app-title", "ABSAR Employee");
        ensureMeta("application-name", "ABSAR Employee");

        let canonical = document.querySelector('link[rel="canonical"][data-employee-discuss-pwa]');
        if (!canonical) {
            canonical = document.createElement("link");
            canonical.rel = "canonical";
            canonical.dataset.employeeDiscussPwa = "1";
            document.head.appendChild(canonical);
        }
        canonical.href = `${window.location.origin}${APP_ROOT}`;

        // Odoo can update <title> after Discuss state changes. On the PWA root we
        // deliberately keep the app title stable so Safari never offers to install
        // the currently bootstrapped employee name as the app name.
        const titleEl = document.querySelector("title");
        if (titleEl && !titleObserver) {
            titleObserver = new MutationObserver(() => {
                if (isCanonicalHome() && document.title !== "Chats") {
                    document.title = "Chats";
                }
            });
            titleObserver.observe(titleEl, { childList: true, subtree: true, characterData: true });
        }
    }

    function applyAppMode() {
        const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
        document.documentElement.classList.toggle("ep-discuss-pwa-standalone", standalone);
        document.body?.classList.toggle("ep-discuss-pwa-standalone", standalone);
    }

    function refreshInstallButtons() {
        const installed = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
        document.querySelectorAll("[data-ep-discuss-install]").forEach((button) => {
            button.classList.toggle("d-none", installed);
            button.disabled = false;
            button.title = installed ? "Employee Portal is installed" : "Install Employee Portal";
        });
    }

    function isSafari() {
        const ua = navigator.userAgent || "";
        return /Safari/i.test(ua) && !/Chrome|CriOS|Chromium|Edg|OPR|Firefox|FxiOS/i.test(ua);
    }

    function isIOS() {
        return /iphone|ipad|ipod/i.test(navigator.userAgent || "") ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    }

    function closeInstallHelp() {
        document.getElementById("ep-discuss-install-help")?.remove();
    }

    function showInstallHelp() {
        closeInstallHelp();
        enforceCanonicalHomeIdentity();

        const overlay = document.createElement("div");
        overlay.id = "ep-discuss-install-help";
        overlay.className = "ep-discuss-install-overlay";

        const logo = document.querySelector('meta[name="employee-discuss-company-logo"]')?.content || "";
        const safari = isSafari();
        const ios = isIOS();
        let instructions;
        if (safari && ios) {
            instructions = "In Safari, tap Share, then choose Add to Home Screen.";
        } else if (safari) {
            instructions = "In Safari, use the Share or File menu and choose Add to Dock.";
        } else {
            instructions = "Use your browser menu and choose Install Chats or Install app.";
        }

        overlay.innerHTML = `
            <div class="ep-discuss-install-card" role="dialog" aria-modal="true" aria-label="Install Chats">
                <button type="button" class="ep-discuss-install-close" aria-label="Close">&times;</button>
                ${logo ? `<img class="ep-discuss-install-logo" src="${logo}" alt=""/>` : ""}
                <h3>Install Chats</h3>
                <p>${instructions}</p>
                <div class="ep-discuss-install-note">Chats will open from this main Discuss page, not from an individual conversation.</div>
                <button type="button" class="btn btn-primary ep-discuss-install-done">OK</button>
            </div>`;
        document.body.appendChild(overlay);
        overlay.querySelector(".ep-discuss-install-close")?.addEventListener("click", closeInstallHelp);
        overlay.querySelector(".ep-discuss-install-done")?.addEventListener("click", closeInstallHelp);
        overlay.addEventListener("click", (event) => {
            if (event.target === overlay) closeInstallHelp();
        });
    }

    function moveToCanonicalInstallRoot() {
        try {
            sessionStorage.setItem("ep-discuss-install-intent", "1");
        } catch (_) {}
        window.location.assign(`${APP_ROOT}?install=1`);
    }

    async function installChats() {
        // Chromium uses the manifest's stable start_url, so its native install
        // prompt can be shown from any conversation safely.
        if (deferredInstallPrompt) {
            deferredInstallPrompt.prompt();
            try {
                await deferredInstallPrompt.userChoice;
            } finally {
                deferredInstallPrompt = null;
                refreshInstallButtons();
            }
            return;
        }

        // Safari installs the CURRENT page. Never let an individual employee/channel
        // URL become the Dock/Home Screen app. Move to the neutral Chats root first.
        if (!isCanonicalHome()) {
            moveToCanonicalInstallRoot();
            return;
        }

        enforceCanonicalHomeIdentity();
        showInstallHelp();
    }

    function handleInstallIntent() {
        if (!isCanonicalHome()) return;
        const params = new URLSearchParams(window.location.search);
        let intent = params.get("install") === "1";
        try {
            intent = intent || sessionStorage.getItem("ep-discuss-install-intent") === "1";
            sessionStorage.removeItem("ep-discuss-install-intent");
        } catch (_) {}
        if (!intent) return;

        // Remove the helper query parameter before Safari creates a Dock/Home Screen
        // entry, so the saved URL is exactly the canonical Chats root.
        window.history.replaceState(window.history.state, "", APP_ROOT);
        enforceCanonicalHomeIdentity();
        window.setTimeout(showInstallHelp, 250);
    }

    function bindHomePage() {
        if (document.documentElement.dataset.epChatsHomeDelegated === "1") return;
        document.documentElement.dataset.epChatsHomeDelegated = "1";

        // Use event delegation so Search and + New chat keep working even after
        // Odoo/browser restores or replaces parts of the page.
        document.addEventListener("click", (event) => {
            const toggle = event.target.closest?.("[data-ep-new-chat-toggle]");
            if (toggle) {
                event.preventDefault();
                event.stopPropagation();
                const modal = document.getElementById("ep-native-new-chat");
                if (!modal) return;
                modal.classList.add("show");
                modal.setAttribute("aria-hidden", "false");
                return;
            }
            const close = event.target.closest?.("[data-ep-new-chat-close]");
            if (close) {
                event.preventDefault();
                const modal = document.getElementById("ep-native-new-chat");
                modal?.classList.remove("show");
                modal?.setAttribute("aria-hidden", "true");
            }
        }, true);

        document.addEventListener("input", (event) => {
            const chatInput = event.target.closest?.("[data-ep-chat-search]");
            if (chatInput) {
                const query = (chatInput.value || "").trim().toLowerCase();
                document.querySelectorAll("[data-ep-thread]").forEach((thread) => {
                    const haystack = (thread.dataset.search || thread.textContent || "").toLowerCase();
                    thread.style.display = !query || haystack.includes(query) ? "" : "none";
                });
                return;
            }
            const peopleInput = event.target.closest?.("[data-ep-new-chat-search]");
            if (peopleInput) {
                const query = (peopleInput.value || "").trim().toLowerCase();
                document.querySelectorAll(".ep-native-person-option").forEach((person) => {
                    const haystack = (person.dataset.search || person.textContent || "").toLowerCase();
                    person.style.display = !query || haystack.includes(query) ? "" : "none";
                });
            }
        }, true);
    }

    function bindInstallButtons() {
        // The visible Install control was intentionally removed. Browser/native
        // installation remains available from the browser UI when desired.
    }


    addHeadMetadata();
    enforceCanonicalHomeIdentity();
    applyAppMode();

    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register(`${APP_ROOT}/sw.js`, { scope: APP_ROOT }).catch((error) => {
                console.warn("Chats PWA service worker registration failed", error);
            });
        }, { once: true });
    }

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredInstallPrompt = event;
        refreshInstallButtons();
    });
    window.addEventListener("appinstalled", () => {
        deferredInstallPrompt = null;
        refreshInstallButtons();
    });

    document.addEventListener("DOMContentLoaded", () => {
        enforceCanonicalHomeIdentity();
        bindInstallButtons();
        bindHomePage();
    });
    window.addEventListener("pageshow", () => {
        enforceCanonicalHomeIdentity();
        applyAppMode();
        bindInstallButtons();
        bindHomePage();
    });

    // Expose only the install action to the native Owl toolbar patch.
    window.EmployeeDiscussPWA = { install: installChats };
})();

// Stable Chats shell navigation. The top-level PWA URL always remains
// /my/employee/discuss; native Odoo Discuss runs only inside the same-origin frame.
(() => {
    const bind = () => {
        const shell = document.querySelector('[data-ep-chats-shell]');
        if (!shell || shell.dataset.epShellBound === '1') return;
        shell.dataset.epShellBound = '1';
        const pane = shell.querySelector('[data-ep-chat-pane]');
        const frame = shell.querySelector('[data-ep-discuss-frame]');
        const empty = shell.querySelector('[data-ep-chat-empty]');
        const listPane = shell.querySelector('[data-ep-chats-list-pane]');
        const openChat = () => {
            shell.classList.add('ep-chat-open');
            empty?.classList.add('d-none');
            frame?.classList.add('show');
        };
        shell.querySelectorAll('[data-ep-thread]').forEach((link) => {
            link.addEventListener('click', (event) => {
                event.preventDefault();
                const mobile = window.matchMedia('(max-width: 767.98px)').matches;
                if (mobile) {
                    const mobileHref = link.dataset.mobileHref || (link.getAttribute('href') || '').replace('?embedded=1', '');
                    if (mobileHref) window.location.assign(mobileHref);
                    return;
                }
                const href = link.getAttribute('href');
                if (!href || !frame) return;
                shell.querySelectorAll('[data-ep-thread]').forEach((row) => row.classList.remove('active'));
                link.classList.add('active');
                frame.classList.remove('show');
                frame.src = href;
                openChat();
            });
        });
        frame?.addEventListener('load', () => {
            if (frame.src && frame.src !== 'about:blank') openChat();
        });
        shell.querySelector('[data-ep-chat-back]')?.addEventListener('click', () => {
            shell.classList.remove('ep-chat-open');
            frame?.classList.remove('show');
            shell.querySelectorAll('[data-ep-thread]').forEach((row) => row.classList.remove('active'));
            try { frame.src = 'about:blank'; } catch (_) {}
        });
        const wanted = Number(new URLSearchParams(window.location.search).get('open_channel') || 0);
        if (wanted) {
            const link = Array.from(shell.querySelectorAll('[data-ep-thread]')).find((row) => row.getAttribute('href')?.includes(`/channel/${wanted}`));
            if (link) {
                link.click();
                const clean = new URL(window.location.href);
                clean.searchParams.delete('open_channel');
                window.history.replaceState({}, '', clean.pathname + clean.search + clean.hash);
            }
        }
    };
    window.addEventListener('message', (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type !== 'employee-discuss-back-to-chats') return;
        const shell = document.querySelector('[data-ep-chats-shell]');
        const frame = document.querySelector('[data-ep-discuss-frame]');
        if (!shell) return;
        shell.classList.remove('ep-chat-open');
        frame?.classList.remove('show');
        shell.querySelectorAll('[data-ep-thread]').forEach((row) => row.classList.remove('active'));
        try { if (frame) frame.src = 'about:blank'; } catch (_) {}
    });
    document.addEventListener('DOMContentLoaded', bind);
    window.addEventListener('pageshow', bind);
})();
