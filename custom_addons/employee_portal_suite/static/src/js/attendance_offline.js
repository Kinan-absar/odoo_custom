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

    function loadState() {
        return safeParse(localStorage.getItem(STATE_KEY) || "{}", {});
    }

    function saveState(state) {
        localStorage.setItem(STATE_KEY, JSON.stringify(state));
    }

    function recomputeState() {
        let state = {
            checkedIn: serverState.checkedIn,
            checkInIso: serverState.serverCheckInIso || null,
        };
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
        return dt.toLocaleString([], {
            day: "2-digit", month: "short", year: "numeric",
            hour: "2-digit", minute: "2-digit",
        });
    }

    function setText(id, value) {
        const el = $(id);
        if (el) el.textContent = value;
    }

    function setVisible(id, visible) {
        const el = $(id);
        if (el) el.hidden = !visible;
    }

    function render() {
        const queue = loadQueue();
        const state = recomputeState();
        const pending = queue.filter((e) => e.status !== "failed");
        const failed = queue.filter((e) => e.status === "failed");
        const isOnline = navigator.onLine;

        setVisible("eps-attendance-checked-in", state.checkedIn);
        setVisible("eps-attendance-checked-out", !state.checkedIn);
        const inHero = $("eps-attendance-checked-in");
        const outHero = $("eps-attendance-checked-out");
        if (inHero) inHero.style.display = state.checkedIn ? "" : "none";
        if (outHero) outHero.style.display = state.checkedIn ? "none" : "";
        setText("eps-attendance-current-status", state.checkedIn ? "Active" : "Inactive");
        setText("eps-offline-checkin-since", state.checkedIn && state.checkInIso ? formatLocal(state.checkInIso) : "");

        const banner = $("eps-attendance-offline-banner");
        if (banner) {
            if (!isOnline) {
                banner.hidden = false;
                banner.className = "portal-alert eps-offline-alert";
                banner.innerHTML = `<i class="fa fa-wifi" aria-hidden="true"></i><span><strong>Offline mode.</strong> Attendance will be saved on this device and synced automatically when internet returns.${pending.length ? ` ${pending.length} event${pending.length === 1 ? "" : "s"} waiting.` : ""}</span>`;
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

        document.querySelectorAll(".eps-attendance-sync-state").forEach((offlineBadge) => {
            if (failed.length) {
                offlineBadge.textContent = "Sync attention needed";
                offlineBadge.dataset.state = "failed";
            } else if (pending.length) {
                offlineBadge.textContent = isOnline ? "Syncing…" : `Saved offline (${pending.length})`;
                offlineBadge.dataset.state = isOnline ? "syncing" : "offline";
            } else {
                offlineBadge.textContent = isOnline ? "Online" : "Offline ready";
                offlineBadge.dataset.state = isOnline ? "online" : "offline";
            }
        });
    }

    function getPosition({required = false} = {}) {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                if (required) reject(new Error("Location is required but this device does not support geolocation."));
                else resolve(null);
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude,
                    accuracy: Number.isFinite(pos.coords.accuracy) ? pos.coords.accuracy : null,
                }),
                (err) => {
                    if (required) reject(err);
                    else resolve(null);
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
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

    async function queueOffline(kind, button) {
        if (button) button.disabled = true;
        try {
            const requiredGeo = kind === "check_in" && serverState.geoEnforce;
            const location = await getPosition({required: requiredGeo});
            const event = {
                id: uuid(),
                kind,
                captured_at: new Date().toISOString(),
                lat: location?.lat ?? null,
                lon: location?.lon ?? null,
                accuracy: location?.accuracy ?? null,
                status: "pending",
            };
            const queue = loadQueue();
            queue.push(event);
            saveQueue(queue);
            render();
        } catch (error) {
            showLocalError(
                error?.code === 1
                    ? "Location access is required to save an offline check-in. Please allow location access and try again."
                    : "Could not get your location. Please try again before leaving this page."
            );
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function submitOnline(kind, form, button) {
        if (!form) return;
        if (button) button.disabled = true;
        try {
            const requiredGeo = kind === "check_in" && serverState.geoEnforce;
            const location = serverState.geoEnforce ? await getPosition({required: requiredGeo}) : null;
            const latInput = form.querySelector('input[name="geo_lat"]');
            const lonInput = form.querySelector('input[name="geo_lon"]');
            if (location && latInput && lonInput) {
                latInput.value = location.lat;
                lonInput.value = location.lon;
            }
            form.submit();
        } catch (error) {
            if (button) button.disabled = false;
            showLocalError(
                error?.code === 1
                    ? "Location access denied. Please allow location access and try again."
                    : "Could not get your location. Please try again."
            );
        }
    }

    async function onAttendanceClick(kind, formId, button) {
        const state = recomputeState();
        if (kind === "check_in" && state.checkedIn) return;
        if (kind === "check_out" && !state.checkedIn) return;
        if (!navigator.onLine) {
            await queueOffline(kind, button);
            return;
        }
        await submitOnline(kind, $(formId), button);
    }

    async function syncQueue() {
        if (!navigator.onLine || window.__epsAttendanceSyncing) return;
        const queue = loadQueue();
        const pending = queue.filter((e) => e.status !== "failed");
        if (!pending.length) {
            render();
            return;
        }
        window.__epsAttendanceSyncing = true;
        render();
        try {
            const response = await fetch("/my/employee/attendance/offline_sync", {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
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
                if (!result) {
                    next.push(event);
                    continue;
                }
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
        if (!navigator.onLine || !("serviceWorker" in navigator)) return;
        try {
            const registration = await navigator.serviceWorker.ready;
            const worker = registration.active || registration.waiting || registration.installing;
            if (!worker) return;
            const assets = performance.getEntriesByType("resource")
                .map((entry) => entry.name)
                .filter((value) => {
                    try {
                        const url = new URL(value, window.location.origin);
                        return url.origin === window.location.origin &&
                            (url.pathname.includes("/web/assets/") || url.pathname.includes("/employee_portal_suite/"));
                    } catch (_) {
                        return false;
                    }
                });
            worker.postMessage({type: "CACHE_ATTENDANCE_OFFLINE", assets});
        } catch (error) {
            console.warn("[EPS Attendance] offline cache preparation deferred", error);
        }
    }

    const checkInBtn = $("checkin-btn");
    if (checkInBtn) {
        checkInBtn.addEventListener("click", () => onAttendanceClick("check_in", "checkin-form", checkInBtn));
    }
    const checkOutBtn = $("checkout-btn");
    if (checkOutBtn) {
        checkOutBtn.addEventListener("click", () => onAttendanceClick("check_out", "checkout-form", checkOutBtn));
    }

    window.addEventListener("online", () => { render(); syncQueue(); });
    window.addEventListener("offline", render);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && navigator.onLine) syncQueue();
    });

    render();
    if (navigator.onLine) {
        primeOfflineCache();
        syncQueue();
    }
})();
