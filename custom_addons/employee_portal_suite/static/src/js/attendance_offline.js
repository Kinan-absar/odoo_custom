(() => {
    if (window.__epsAttendanceOfflineLoaded) return;
    window.__epsAttendanceOfflineLoaded = true;

    const PATH = "/my/employee/attendance";
    const MAX_QUEUE = 100;
    if (!window.location.pathname.startsWith(PATH)) return;

    const $ = (id) => document.getElementById(id);
    const root = document.querySelector("[data-eps-attendance-root]");
    if (!root) return;

    const userScope = root.dataset.userId || "unknown";
    const QUEUE_KEY = `eps_attendance_offline_queue_v1:${userScope}`;
    const STATE_KEY = `eps_attendance_offline_state_v1:${userScope}`;
    const DEVICE_KEY = `eps_attendance_trusted_device_v1:${userScope}`;
    const OFFLINE_READY_KEY = `eps_attendance_offline_ready_v48:${userScope}`;

    const serverState = {
        checkedIn: root.dataset.serverCheckedIn === "1",
        geoEnforce: root.dataset.geoEnforce === "1",
        serverCheckInIso: root.dataset.serverCheckInIso || "",
    };

    function safeParse(raw, fallback) {
        try { return JSON.parse(raw); } catch (_) { return fallback; }
    }
    function loadQueue() {
        const value = safeParse(localStorage.getItem(QUEUE_KEY) || "[]", []);
        return Array.isArray(value) ? value : [];
    }
    function saveQueue(queue) {
        localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
    }
    function saveState(state) { localStorage.setItem(STATE_KEY, JSON.stringify(state)); }
    function loadDevice() {
        const value = safeParse(localStorage.getItem(DEVICE_KEY) || "{}", {});
        return value && typeof value === "object" ? value : {};
    }
    function saveDevice(device) { localStorage.setItem(DEVICE_KEY, JSON.stringify(device)); }
    function offlineCacheReady() { return localStorage.getItem(OFFLINE_READY_KEY) === '1'; }
    function setOfflineCacheReady(ready) {
        if (ready) localStorage.setItem(OFFLINE_READY_KEY, '1');
        else localStorage.removeItem(OFFLINE_READY_KEY);
    }

    function secureToken() {
        const bytes = new Uint8Array(32);
        if (window.crypto?.getRandomValues) {
            window.crypto.getRandomValues(bytes);
            return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
        }
        return `${Date.now()}-${Math.random()}-${Math.random()}-${Math.random()}`.replace(/\./g, "");
    }
    function ensureDevice() {
        let device = loadDevice();
        if (!device.token || String(device.token).length < 32) {
            device = {token: secureToken(), state: "unknown", created_at: new Date().toISOString()};
            saveDevice(device);
        }
        return device;
    }
    function deviceLabel() {
        const platform = navigator.userAgentData?.platform || navigator.platform || "Mobile device";
        const standalone = window.matchMedia?.("(display-mode: standalone)")?.matches ? "PWA" : "Browser";
        return `${platform} · ${standalone}`.slice(0, 128);
    }
    function deviceIsTrusted() { return loadDevice().state === "trusted"; }

    function recomputeState() {
        let state = {checkedIn: serverState.checkedIn, checkInIso: serverState.serverCheckInIso || null};
        for (const event of loadQueue()) {
            if (event.status === "failed") continue;
            if (event.kind === "check_in") {
                state.checkedIn = true;
                state.checkInIso = event.captured_at;
            } else if (event.kind === "check_out") {
                state.checkedIn = false;
                state.checkInIso = null;
            }
        }
        saveState(state);
        return state;
    }
    function uuid() {
        if (crypto?.randomUUID) return crypto.randomUUID();
        return `eps-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
    function formatLocal(iso) {
        if (!iso) return "";
        const dt = new Date(iso);
        if (Number.isNaN(dt.getTime())) return "";
        return dt.toLocaleString([], {day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"});
    }
    function setText(id, value) { const el = $(id); if (el) el.textContent = value; }
    function setVisible(id, visible) { const el = $(id); if (el) el.hidden = !visible; }

    function applyDeviceToForms() {
        const device = ensureDevice();
        document.querySelectorAll('input[name="trusted_device_token"]').forEach((input) => { input.value = device.token; });
    }

    function render() {
        const queue = loadQueue();
        const state = recomputeState();
        const device = ensureDevice();
        const pending = queue.filter((e) => e.status !== "failed");
        const failed = queue.filter((e) => e.status === "failed");
        const isOnline = navigator.onLine;
        const trusted = device.state === "trusted";

        setVisible("eps-attendance-checked-in", state.checkedIn);
        setVisible("eps-attendance-checked-out", !state.checkedIn);
        const inHero = $("eps-attendance-checked-in");
        const outHero = $("eps-attendance-checked-out");
        if (inHero) inHero.style.display = state.checkedIn ? "" : "none";
        if (outHero) outHero.style.display = state.checkedIn ? "none" : "";
        setText("eps-attendance-current-status", state.checkedIn ? "Active" : "Inactive");
        setText("eps-offline-checkin-since", state.checkedIn && state.checkInIso ? formatLocal(state.checkInIso) : "");

        const checkInBtn = $("checkin-btn");
        const checkOutBtn = $("checkout-btn");
        if (checkInBtn) checkInBtn.disabled = !trusted;
        if (checkOutBtn) checkOutBtn.disabled = !trusted;
        applyDeviceToForms();

        const banner = $("eps-attendance-offline-banner");
        if (banner) {
            if (device.state === "pending") {
                banner.hidden = false;
                banner.className = "portal-alert error";
                banner.innerHTML = '<i class="fa fa-mobile" aria-hidden="true"></i><span><strong>This phone is not approved for attendance.</strong> A trusted phone is already registered. Ask the Attendance Manager to approve this device and replace the old one.</span>';
            } else if (device.state === "revoked") {
                banner.hidden = false;
                banner.className = "portal-alert error";
                banner.innerHTML = '<i class="fa fa-ban" aria-hidden="true"></i><span><strong>This attendance device has been revoked.</strong> Ask the Attendance Manager to approve this phone again.</span>';
            } else if (!trusted && !isOnline) {
                banner.hidden = false;
                banner.className = "portal-alert error";
                banner.innerHTML = '<i class="fa fa-lock" aria-hidden="true"></i><span><strong>Attendance unavailable offline.</strong> This phone must be verified online as the employee\'s trusted device first.</span>';
            } else if (!trusted && isOnline) {
                banner.hidden = false;
                banner.className = "portal-alert eps-sync-alert";
                banner.innerHTML = '<i class="fa fa-refresh fa-spin" aria-hidden="true"></i><span>Verifying this phone for attendance…</span>';
            } else if (!isOnline) {
                banner.hidden = false;
                banner.className = "portal-alert eps-offline-alert";
                banner.innerHTML = `<i class="fa fa-wifi" aria-hidden="true"></i><span><strong>Offline mode · Trusted device.</strong> Attendance will be saved on this phone and synced automatically when internet returns.${pending.length ? ` ${pending.length} event${pending.length === 1 ? "" : "s"} waiting.` : ""}</span>`;
            } else if (failed.length) {
                banner.hidden = false;
                banner.className = "portal-alert error";
                banner.innerHTML = `<i class="fa fa-exclamation-circle" aria-hidden="true"></i><span>${failed.length} offline attendance event${failed.length === 1 ? "" : "s"} could not sync. Open this page online and contact HR if the message remains.</span>`;
            } else if (pending.length) {
                banner.hidden = false;
                banner.className = "portal-alert eps-sync-alert";
                banner.innerHTML = `<i class="fa fa-refresh fa-spin" aria-hidden="true"></i><span>Syncing ${pending.length} offline attendance event${pending.length === 1 ? "" : "s"}…</span>`;
            } else {
                banner.hidden = true;
                banner.textContent = "";
            }
        }

        document.querySelectorAll(".eps-attendance-sync-state").forEach((badge) => {
            if (!trusted) {
                badge.textContent = device.state === "pending" ? "Device approval needed" : "Verifying device";
                badge.dataset.state = "failed";
            } else if (failed.length) {
                badge.textContent = "Sync attention needed";
                badge.dataset.state = "failed";
            } else if (pending.length) {
                badge.textContent = isOnline ? "Syncing…" : `Saved offline (${pending.length})`;
                badge.dataset.state = isOnline ? "syncing" : "offline";
            } else {
                if (isOnline) {
                    badge.textContent = offlineCacheReady() ? "Offline Ready · Trusted" : "Preparing Offline…";
                    badge.dataset.state = offlineCacheReady() ? "online" : "syncing";
                } else {
                    badge.textContent = offlineCacheReady() ? "Offline Ready · Trusted" : "Offline · Page not cached";
                    badge.dataset.state = offlineCacheReady() ? "offline" : "failed";
                }
            }
        });
    }

    async function verifyDevice() {
        if (!navigator.onLine) { render(); return deviceIsTrusted(); }
        const device = ensureDevice();
        try {
            const response = await fetch("/my/employee/attendance/device/status", {
                method: "POST", credentials: "same-origin", cache: "no-store",
                headers: {"Content-Type": "application/json", "Accept": "application/json"},
                body: JSON.stringify({token: device.token, device_label: deviceLabel()}),
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            device.state = payload.state || "unknown";
            device.last_verified_at = new Date().toISOString();
            saveDevice(device);
            render();
            return device.state === "trusted";
        } catch (error) {
            console.warn("[EPS Attendance] trusted-device verification deferred", error);
            render();
            return deviceIsTrusted();
        }
    }

    function getPosition({required = false} = {}) {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                if (required) reject(new Error("Location is required but this device does not support geolocation."));
                else resolve(null);
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null}),
                (err) => required ? reject(err) : resolve(null),
                {enableHighAccuracy: true, timeout: 10000, maximumAge: 0},
            );
        });
    }

    function showLocalError(message) {
        const banner = $("eps-attendance-offline-banner");
        if (!banner) return;
        banner.hidden = false;
        banner.className = "portal-alert error";
        banner.innerHTML = `<i class="fa fa-exclamation-circle" aria-hidden="true"></i><span>${String(message || "Attendance could not be saved.")}</span>`;
    }

    async function queueOffline(kind, button, capturedLocation = undefined) {
        const device = ensureDevice();
        if (device.state !== "trusted") {
            showLocalError("Attendance is blocked because this phone has not been verified as the employee's trusted device.");
            return false;
        }
        if (button) button.disabled = true;
        try {
            const requiredGeo = kind === "check_in" && serverState.geoEnforce;
            const location = capturedLocation === undefined
                ? await getPosition({required: requiredGeo})
                : capturedLocation;
            if (requiredGeo && !location) throw new Error("location_required");
            const event = {
                id: uuid(), kind, captured_at: new Date().toISOString(),
                lat: location?.lat ?? null, lon: location?.lon ?? null, accuracy: location?.accuracy ?? null,
                device_token: device.token, status: "pending",
            };
            const queue = loadQueue();
            queue.push(event);
            saveQueue(queue);
            render();
            return true;
        } catch (error) {
            showLocalError(error?.code === 1
                ? "Location access is required to save an offline check-in. Please allow location access and try again."
                : "Could not get your location. Please try again before leaving this page.");
            return false;
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function submitOnline(kind, form, button) {
        if (!form) return;
        if (!(await verifyDevice())) {
            showLocalError("Attendance is blocked on this phone until it is approved as the trusted attendance device.");
            return;
        }
        if (button) button.disabled = true;
        let location;
        try {
            const requiredGeo = kind === "check_in" && serverState.geoEnforce;
            location = serverState.geoEnforce ? await getPosition({required: requiredGeo}) : null;
            const latInput = form.querySelector('input[name="geo_lat"]');
            const lonInput = form.querySelector('input[name="geo_lon"]');
            const tokenInput = form.querySelector('input[name="trusted_device_token"]');
            if (location && latInput && lonInput) { latInput.value = location.lat; lonInput.value = location.lon; }
            if (tokenInput) tokenInput.value = ensureDevice().token;

            // Do not trust navigator.onLine on mobile/PWA. Submit with fetch so a
            // real network failure can be detected and converted into an offline
            // attendance event instead of sending the PWA to a browser error page.
            const response = await fetch(form.action, {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
                redirect: "follow",
                body: new FormData(form),
            });
            if (!response.ok) throw new Error(`attendance_http_${response.status}`);
            const finalUrl = response.url || PATH;
            window.location.assign(finalUrl);
        } catch (error) {
            const networkFailure = error instanceof TypeError || !navigator.onLine;
            if (networkFailure) {
                const queued = await queueOffline(kind, button, location);
                if (queued) return;
            } else {
                showLocalError(error?.code === 1
                    ? "Location access denied. Please allow location access and try again."
                    : "Attendance could not be submitted. Please try again.");
            }
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function onAttendanceClick(kind, formId, button) {
        const state = recomputeState();
        if (kind === "check_in" && state.checkedIn) return;
        if (kind === "check_out" && !state.checkedIn) return;
        if (!deviceIsTrusted()) {
            if (navigator.onLine) await verifyDevice();
            if (!deviceIsTrusted()) {
                showLocalError("Attendance is blocked on this phone until it is approved as the employee's trusted attendance device.");
                return;
            }
        }
        if (!navigator.onLine) { await queueOffline(kind, button); return; }
        await submitOnline(kind, $(formId), button);
    }

    async function syncQueue() {
        if (!navigator.onLine || window.__epsAttendanceSyncing) return;
        if (!(await verifyDevice())) return;
        const queue = loadQueue();
        const pending = queue.filter((e) => e.status !== "failed");
        if (!pending.length) { render(); return; }
        window.__epsAttendanceSyncing = true;
        render();
        try {
            const response = await fetch("/my/employee/attendance/offline_sync", {
                method: "POST", credentials: "same-origin", cache: "no-store",
                headers: {"Content-Type": "application/json", "Accept": "application/json"},
                body: JSON.stringify({events: pending}),
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            if (!payload || !Array.isArray(payload.results)) throw new Error("Invalid sync response");
            const byId = new Map(payload.results.map((r) => [r.id, r]));
            const next = [];
            for (const event of queue) {
                const result = byId.get(event.id);
                if (!result) { next.push(event); continue; }
                if (result.status === "synced" || result.status === "duplicate") continue;
                next.push({...event, status: "failed", error: result.message || result.code || "sync_failed"});
            }
            saveQueue(next);
            if (!next.length) {
                saveState({checkedIn: Boolean(payload.is_checked_in), checkInIso: payload.open_check_in || null});
                window.location.reload();
                return;
            }
        } catch (error) {
            console.warn("[EPS Attendance] offline sync deferred", error);
        } finally {
            window.__epsAttendanceSyncing = false;
            render();
        }
    }

    async function primeOfflineCache() {
        if (!("serviceWorker" in navigator)) return false;
        try {
            const registration = await navigator.serviceWorker.ready;
            const worker = registration.active || registration.waiting || registration.installing;
            if (!worker) return false;
            const assets = performance.getEntriesByType("resource").map((entry) => entry.name).filter((value) => {
                try {
                    const url = new URL(value, window.location.origin);
                    return url.origin === window.location.origin && (url.pathname.includes("/web/assets/") || url.pathname.includes("/employee_portal_suite/"));
                } catch (_) { return false; }
            });
            const channel = new MessageChannel();
            const result = new Promise((resolve) => {
                const timer = window.setTimeout(() => resolve(false), 12000);
                channel.port1.onmessage = (event) => {
                    window.clearTimeout(timer);
                    resolve(Boolean(event.data?.ok));
                };
            });
            worker.postMessage({type: "CACHE_ATTENDANCE_OFFLINE", assets}, [channel.port2]);
            const ready = await result;
            setOfflineCacheReady(ready);
            render();
            return ready;
        } catch (error) {
            console.warn("[EPS Attendance] offline cache preparation deferred", error);
            setOfflineCacheReady(false);
            render();
            return false;
        }
    }

    const checkInBtn = $("checkin-btn");
    if (checkInBtn) checkInBtn.addEventListener("click", () => onAttendanceClick("check_in", "checkin-form", checkInBtn));
    const checkOutBtn = $("checkout-btn");
    if (checkOutBtn) checkOutBtn.addEventListener("click", () => onAttendanceClick("check_out", "checkout-form", checkOutBtn));

    window.addEventListener("online", async () => { await verifyDevice(); render(); syncQueue(); });
    window.addEventListener("offline", render);
    document.addEventListener("visibilitychange", () => { if (!document.hidden && navigator.onLine) verifyDevice().then(syncQueue); });

    ensureDevice();
    render();
    if (navigator.onLine) {
        primeOfflineCache();
        verifyDevice().then(syncQueue);
    } else {
        render();
    }
})();
