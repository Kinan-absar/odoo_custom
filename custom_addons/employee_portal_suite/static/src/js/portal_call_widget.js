/**
 * Employee Portal Suite - Calling widget.
 *
 * Deliberately framework-light (no OWL/publicWidget/bus_service dependency)
 * so the exact same file can be loaded in both web.assets_frontend (portal)
 * and web.assets_backend (internal users) and behave identically.
 *
 * Signalling is done by polling /employee_portal/call/poll every 2s rather
 * than using the mail bus, to keep this fully decoupled from Discuss/RTC
 * internals. See portal_call.py controller docstring for the tradeoffs.
 */
(function () {
    "use strict";

    const POLL_INTERVAL_MS = 2000;
    const PRESENCE_INTERVAL_MS = 15000;

    async function rpc(route, params) {
        const resp = await fetch(route, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: params || {},
                id: Math.floor(Math.random() * 1e9),
            }),
        });
        const json = await resp.json();
        if (json.error) {
            console.error("[EPC] RPC error", json.error);
            throw new Error(json.error.data ? json.error.data.message : "RPC error");
        }
        return json.result;
    }

    class EmployeePortalCaller {
        constructor() {
            this.lastId = 0;
            this.pollTimer = null;
            this.pc = null; // legacy alias for first peer
            this.peerConnections = new Map();
            this.peerNames = new Map();
            this.localStream = null;
            this.currentUuid = null;
            this.currentCallType = "audio";
            this.iceServers = [{ urls: ["stun:stun.l.google.com:19302"] }];
            this.contacts = [];
            this.currentPeerName = "";
            this.ringTimer = null;
            this.ringContext = null;
            this.ringGain = null;
            this.callStartedAt = null;
            this.callTimer = null;
            this.screenStream = null;
            this.screenTrack = null;
            this._cameraTrackBeforeShare = null;
            this._addingPeople = false;
            this.speakerEnabled = false;
            this.speakerSinkId = null;
            this.defaultSinkId = null;
            this.pendingIceCandidates = new Map();
            this.participants = [];
            this.groupCallMode = false;
            this.groupSelection = new Set();
            this.presenceTimer = null;
            this.callHistory = [];
            this.historyTimer = null;
            this.panelView = "people";
            this.unreadMissedCount = 0;
            this._lastLocalActivity = Date.now();
            this.selfUserId = null;
            this.reconnectTimers = new Map();
            this.reconnectAttempts = new Map();
            this.peerConnectionStates = new Map();
            this._networkOffline = !navigator.onLine;
            this._buildUI();
            this._bindPresenceActivity();
            this._bindNetworkRecovery();
            this._loadContacts();
            this._startPresenceHeartbeat();
            this._startHistoryRefresh();
            this._startPolling();
        }

        // ------------------------------------------------------------
        // UI scaffolding (framework independent, injected once)
        // ------------------------------------------------------------
        _buildUI() {
            const root = document.createElement("div");
            root.id = "epc-root";
            root.innerHTML = `
                <button id="epc-fab" class="epc-fallback-fab epc-hidden" title="Call" aria-label="Call"><i class="fa fa-phone"></i></button>
                <div id="epc-picker-backdrop" class="epc-hidden"></div>
                <div id="epc-panel" class="epc-hidden">
                    <div class="epc-panel-header">
                        <span>Calls</span>
                        <button id="epc-panel-close">&times;</button>
                    </div>
                    <div id="epc-panel-tabs" class="epc-panel-tabs">
                        <button id="epc-tab-people" type="button" class="epc-panel-tab epc-active"><i class="fa fa-users"></i><span>People</span></button>
                        <button id="epc-tab-history" type="button" class="epc-panel-tab"><i class="fa fa-history"></i><span>Recent</span><span id="epc-tab-missed" class="epc-tab-badge epc-hidden">0</span></button>
                    </div>
                    <div id="epc-people-view">
                    <div class="epc-search-wrap"><input id="epc-contact-search" type="search" placeholder="Search employees…" autocomplete="off"/></div>
                    <div id="epc-call-mode-bar" class="epc-call-mode-bar">
                        <button id="epc-group-mode" type="button" class="epc-group-mode-btn"><i class="fa fa-users"></i><span>Group call</span></button>
                        <div id="epc-group-actions" class="epc-group-actions epc-hidden">
                            <span id="epc-group-count">0 selected</span>
                            <button id="epc-start-group" type="button" class="epc-btn epc-btn-small" disabled><i class="fa fa-phone"></i><span>Start call</span></button>
                        </div>
                    </div>
                    <div id="epc-contact-list"><div class="epc-empty">Loading…</div></div>
                    </div>
                    <div id="epc-history-view" class="epc-hidden">
                        <div id="epc-history-list"><div class="epc-empty">Loading recent calls…</div></div>
                    </div>
                </div>
                <div id="epc-incoming" class="epc-hidden">
                    <div class="epc-call-avatar epc-incoming-avatar"><img id="epc-incoming-photo" class="epc-avatar-photo epc-hidden" alt=""/><span id="epc-incoming-fallback"><i class="fa fa-phone"></i></span></div>
                    <div class="epc-incoming-name"></div>
                    <div class="epc-incoming-sub">Incoming audio call</div>
                    <div class="epc-incoming-actions">
                        <button id="epc-reject" class="epc-call-action epc-call-action-decline" title="Decline"><i class="fa fa-phone"></i><span>Decline</span></button>
                        <button id="epc-accept" class="epc-call-action epc-call-action-accept" title="Accept"><i class="fa fa-phone"></i><span>Accept</span></button>
                    </div>
                </div>
                <div id="epc-active" class="epc-hidden epc-audio-call">
                    <div class="epc-active-stage">
                        <div class="epc-call-avatar epc-active-avatar"><img id="epc-peer-photo" class="epc-avatar-photo epc-hidden" alt=""/><span id="epc-peer-initial">?</span></div>
                        <div class="epc-active-name">Employee</div>
                        <div class="epc-active-status">Connecting…</div>
                        <div class="epc-call-timer">00:00</div>
                    </div>
                    <div class="epc-video-stage epc-hidden">
                        <video id="epc-remote-video" autoplay playsinline></video>
                        <video id="epc-local-video" autoplay playsinline muted></video>
                        <button id="epc-fullscreen" class="epc-fullscreen-btn" type="button" title="Full screen" aria-label="Full screen"><i class="fa fa-expand"></i></button>
                    </div>
                    <div class="epc-participants-wrap">
                        <div class="epc-participants-title"><span>In meeting</span><span id="epc-participant-count">1</span></div>
                        <div id="epc-participant-list" class="epc-participant-list"></div>
                    </div>
                    <div class="epc-active-actions">
                        <button id="epc-mute" class="epc-round-control" title="Mute"><i class="fa fa-microphone"></i><span>Mute</span></button>
                        <button id="epc-add-people" class="epc-round-control" title="Add people"><i class="fa fa-user-plus"></i><span>Add people</span></button>
                        <button id="epc-speaker" class="epc-round-control epc-mobile-only" title="Speaker"><i class="fa fa-volume-up"></i><span>Speaker</span></button>
                        <button id="epc-share-screen" class="epc-round-control epc-desktop-only" title="Share screen"><i class="fa fa-desktop"></i><span>Share screen</span></button>
                        <button id="epc-hangup" class="epc-round-control epc-hangup-control" title="Hang up"><i class="fa fa-phone"></i><span>Hang up</span></button>
                    </div>
                </div>
            `;
            document.body.appendChild(root);

            // Portal: place the phone directly beside every notification bell.
            const bellWraps = Array.from(document.querySelectorAll(".ep-bell-wrap"));
            bellWraps.forEach((bellWrap) => this._addPortalHeaderButton(bellWrap));

            // Backend: Odoo builds the systray after the web client starts, so
            // inject the phone into .o_menu_systray and keep watching until the
            // navbar exists. No bottom-right floating button is used anymore.
            this._ensureBackendSystrayButton();
            if (document.querySelector(".o_web_client")) {
                this._systrayObserver = new MutationObserver(() => this._ensureBackendSystrayButton());
                this._systrayObserver.observe(document.body, { childList: true, subtree: true });
            }
            const closePicker = () => this._closeContactPanel();
            document.getElementById("epc-panel-close").addEventListener("click", closePicker);
            document.getElementById("epc-picker-backdrop").addEventListener("click", closePicker);
            document.getElementById("epc-tab-people").addEventListener("click", (ev) => { ev.stopPropagation(); this._showPanelView("people"); });
            document.getElementById("epc-tab-history").addEventListener("click", (ev) => { ev.stopPropagation(); this._showPanelView("history", true); });
            document.getElementById("epc-accept").addEventListener("click", () => this._acceptIncoming());
            document.getElementById("epc-reject").addEventListener("click", () => this._rejectIncoming());
            document.getElementById("epc-hangup").addEventListener("click", () => this._hangup());
            document.getElementById("epc-mute").addEventListener("click", () => this._toggleMute());
            document.getElementById("epc-speaker").addEventListener("click", () => this._toggleSpeaker());
            document.getElementById("epc-add-people").addEventListener("click", (ev) => {
                // Stop the global outside-click handler from immediately closing
                // the picker on the same click that opens it.
                ev.preventDefault();
                ev.stopPropagation();
                this._addingPeople = true;
                this._showPanelView("people", false);
                const panel = document.getElementById("epc-panel");
                panel.classList.add("epc-meeting-picker");
                document.getElementById("epc-picker-backdrop").classList.remove("epc-hidden");
                panel.querySelector(".epc-panel-header span").textContent = "Add people";
                const search = document.getElementById("epc-contact-search");
                if (search) search.value = "";
                this._panelAnchor = ev.currentTarget;
                panel.classList.remove("epc-hidden");
                this._positionPanel(ev.currentTarget);
                this._renderContacts();
                if (search) setTimeout(() => search.focus(), 0);
            });
            document.getElementById("epc-share-screen").addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                this._toggleScreenShare();
            });
            document.getElementById("epc-fullscreen").addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                this._toggleFullscreen();
            });
            document.getElementById("epc-contact-search").addEventListener("input", () => this._renderContacts());
            document.getElementById("epc-group-mode").addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                if (this._addingPeople || this.currentUuid) return;
                this._setGroupCallMode(!this.groupCallMode);
            });
            document.getElementById("epc-start-group").addEventListener("click", (ev) => {
                ev.preventDefault();
                ev.stopPropagation();
                this._startGroupCall();
            });

            // Browsers only allow notification permission prompts and audio-context
            // activation from a user gesture. Any first interaction with the calling
            // UI unlocks both so future incoming calls can ring/notify in background tabs.
            document.addEventListener("pointerdown", (ev) => {
                if (ev.target.closest(".epc-header-btn, .epc-backend-systray-btn, #epc-panel, #epc-incoming, #epc-active")) {
                    this._unlockCallAlerts();
                }
            }, { passive: true });

            document.addEventListener("click", (ev) => {
                const panel = document.getElementById("epc-panel");
                if (!panel.classList.contains("epc-hidden") &&
                    !ev.target.closest("#epc-panel") &&
                    !ev.target.closest(".epc-header-btn") &&
                    !ev.target.closest("#epc-fab")) {
                    this._closeContactPanel();
                }
            });
            this._updateScreenShareAvailability();
            window.addEventListener("resize", () => {
                this._updateScreenShareAvailability();
                const panel = document.getElementById("epc-panel");
                if (!panel.classList.contains("epc-hidden") && this._panelAnchor) {
                    this._positionPanel(this._panelAnchor);
                }
            });
        }

        _addPortalHeaderButton(bellWrap) {
            if (!bellWrap || !bellWrap.parentElement) return;
            if (bellWrap.parentElement.querySelector(":scope > .epc-header-btn")) return;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "epc-header-btn";
            btn.title = "Calls";
            btn.setAttribute("aria-label", "Calls");
            btn.innerHTML = '<i class="fa fa-phone"></i><span class="epc-call-badge epc-hidden">0</span>';
            bellWrap.insertAdjacentElement("beforebegin", btn);
            btn.addEventListener("click", (ev) => {
                ev.stopPropagation();
                this._togglePanel(btn);
            });
        }

        _ensureBackendSystrayButton() {
            if (!document.querySelector(".o_web_client")) return;
            const systray = document.querySelector(".o_menu_systray");
            if (!systray || systray.querySelector(".epc-backend-systray-item")) return;

            const item = document.createElement("div");
            item.className = "o_menu_systray_item epc-backend-systray-item";
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "epc-backend-systray-btn";
            btn.title = "Calls";
            btn.setAttribute("aria-label", "Calls");
            btn.innerHTML = '<i class="fa fa-phone"></i><span class="epc-call-badge epc-hidden">0</span>';
            item.appendChild(btn);
            this._setMissedBadge(this.unreadMissedCount);
            // Put Calls at the leading edge of the systray, beside Odoo status indicator.
            systray.insertBefore(item, systray.firstElementChild);
            btn.addEventListener("click", (ev) => {
                ev.stopPropagation();
                this._togglePanel(btn);
            });
        }

        _togglePanel(anchor) {
            this._unlockCallAlerts(true);
            const panel = document.getElementById("epc-panel");
            const opening = panel.classList.contains("epc-hidden");
            if (opening) {
                if (!this.currentUuid) this._setGroupCallMode(false);
                if (!this._addingPeople) this._showPanelView(this.panelView || "people", false);
                this._panelAnchor = anchor;
                panel.classList.remove("epc-hidden");
                this._positionPanel(anchor);
                const search = document.getElementById("epc-contact-search");
                if (search) setTimeout(() => search.focus(), 0);
            } else {
                panel.classList.add("epc-hidden");
            }
        }

        _closeContactPanel() {
            const panel = document.getElementById("epc-panel");
            if (panel) {
                panel.classList.add("epc-hidden");
                panel.classList.remove("epc-meeting-picker");
                const title = panel.querySelector(".epc-panel-header span");
                if (title) title.textContent = "Calls";
            }
            const backdrop = document.getElementById("epc-picker-backdrop");
            if (backdrop) backdrop.classList.add("epc-hidden");
            this._addingPeople = false;
            this._setGroupCallMode(false);
        }

        _showPanelView(view, markSeen) {
            if (this._addingPeople) view = "people";
            this.panelView = view === "history" ? "history" : "people";
            const people = document.getElementById("epc-people-view");
            const history = document.getElementById("epc-history-view");
            const peopleTab = document.getElementById("epc-tab-people");
            const historyTab = document.getElementById("epc-tab-history");
            if (people) people.classList.toggle("epc-hidden", this.panelView !== "people");
            if (history) history.classList.toggle("epc-hidden", this.panelView !== "history");
            if (peopleTab) peopleTab.classList.toggle("epc-active", this.panelView === "people");
            if (historyTab) historyTab.classList.toggle("epc-active", this.panelView === "history");
            if (this.panelView === "history") {
                this._renderCallHistory();
                if (markSeen) this._markMissedCallsSeen();
            }
        }

        _setMissedBadge(count) {
            const n = Math.max(0, Number(count || 0));
            this.unreadMissedCount = n;
            document.querySelectorAll(".epc-call-badge").forEach((badge) => {
                badge.textContent = n > 99 ? "99+" : String(n);
                badge.classList.toggle("epc-hidden", n === 0);
            });
            const tabBadge = document.getElementById("epc-tab-missed");
            if (tabBadge) {
                tabBadge.textContent = n > 99 ? "99+" : String(n);
                tabBadge.classList.toggle("epc-hidden", n === 0);
            }
        }

        _startHistoryRefresh() {
            const refresh = async () => {
                await this._refreshCallHistory();
                this.historyTimer = setTimeout(refresh, 15000);
            };
            refresh();
        }

        async _refreshCallHistory() {
            try {
                const res = await rpc("/employee_portal/call/history", { limit: 40 });
                this.callHistory = (res && res.calls) || [];
                this._setMissedBadge((res && res.unread_missed_count) || 0);
                if (this.panelView === "history") this._renderCallHistory();
            } catch (e) {
                // History is secondary; never interrupt calling if it cannot load.
            }
        }

        async _markMissedCallsSeen() {
            try {
                await rpc("/employee_portal/call/history/mark_seen", {});
                this._setMissedBadge(0);
                this.callHistory.forEach((item) => { if (item.status === "missed") item.missed_unread = false; });
                this._renderCallHistory();
            } catch (e) {}
        }

        _formatCallDuration(seconds) {
            const total = Math.max(0, Number(seconds || 0));
            if (!total) return "";
            const mins = Math.floor(total / 60);
            const secs = total % 60;
            return mins ? `${mins}m ${String(secs).padStart(2, "0")}s` : `${secs}s`;
        }

        _formatCallTime(value) {
            if (!value) return "";
            const iso = value.includes("T") ? value : value.replace(" ", "T") + "Z";
            const date = new Date(iso);
            if (Number.isNaN(date.getTime())) return value;
            const now = new Date();
            const sameDay = date.toDateString() === now.toDateString();
            return sameDay
                ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                : date.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }

        _historyStatusLabel(item) {
            const labels = {
                completed: item.direction === "outgoing" ? "Outgoing" : "Incoming",
                ongoing: "In progress",
                missed: "Missed",
                declined: "Declined",
                no_answer: "No answer",
                ringing: item.direction === "outgoing" ? "Calling" : "Incoming",
            };
            return labels[item.status] || "Call";
        }

        _renderCallHistory() {
            const list = document.getElementById("epc-history-list");
            if (!list) return;
            list.innerHTML = "";
            if (!this.callHistory.length) {
                list.innerHTML = '<div class="epc-empty">No recent calls yet.</div>';
                return;
            }
            this.callHistory.forEach((item) => {
                const row = document.createElement("div");
                row.className = "epc-history-row" + (item.missed_unread ? " epc-history-unread" : "");
                const iconClass = item.is_group ? "fa-users" : (item.direction === "outgoing" ? "fa-phone" : "fa-phone");
                const statusClass = `epc-history-${this._escape(item.status || "completed")}`;
                const initial = this._escape((item.title || "?").charAt(0).toUpperCase());
                const avatar = item.avatar_url
                    ? `<span class="epc-history-avatar"><img src="${this._escape(item.avatar_url)}" alt="" onerror="this.style.display='none'"/><span>${initial}</span></span>`
                    : `<span class="epc-history-avatar epc-history-group-avatar"><i class="fa ${iconClass}"></i></span>`;
                const duration = this._formatCallDuration(item.duration_seconds);
                row.innerHTML = `${avatar}<div class="epc-history-copy"><div class="epc-history-name">${this._escape(item.title || "Employee")}</div><div class="epc-history-meta"><span class="${statusClass}">${this._escape(this._historyStatusLabel(item))}</span><span>${this._escape(this._formatCallTime(item.started_at))}</span>${duration ? `<span>${this._escape(duration)}</span>` : ""}</div></div>`;
                const callbackIds = (item.callback_user_ids || []).map(Number).filter(Boolean);
                if (callbackIds.length) {
                    const callBtn = document.createElement("button");
                    callBtn.type = "button";
                    callBtn.className = "epc-history-call-btn";
                    callBtn.title = item.is_group ? "Call group again" : "Call again";
                    callBtn.innerHTML = '<i class="fa fa-phone"></i>';
                    callBtn.addEventListener("click", (ev) => {
                        ev.stopPropagation();
                        if (callbackIds.length > 1) this._startHistoryGroupCall(callbackIds);
                        else this._startCall(callbackIds[0]);
                    });
                    row.appendChild(callBtn);
                }
                list.appendChild(row);
            });
        }

        async _startHistoryGroupCall(userIds) {
            if (!userIds || userIds.length < 2) return;
            try {
                const res = await rpc("/employee_portal/call/start", { target_user_ids: userIds, call_type: "audio" });
                if (res.error) { alert("Could not start group call: " + res.error); return; }
                this.currentUuid = res.uuid;
                this._iAmCaller = true;
                this._setPeerName("Group call");
                this._closeContactPanel();
                await this._prepareLocalMedia();
                this._showActive(`Calling ${userIds.length} employees…`);
                await this._refreshParticipants();
            } catch (e) { alert("Could not start group call."); }
        }

        _setGroupCallMode(enabled) {
            this.groupCallMode = Boolean(enabled) && !this.currentUuid && !this._addingPeople;
            if (!this.groupCallMode) this.groupSelection.clear();
            const panel = document.getElementById("epc-panel");
            const modeBtn = document.getElementById("epc-group-mode");
            const actions = document.getElementById("epc-group-actions");
            if (panel) {
                panel.classList.toggle("epc-group-call-mode", this.groupCallMode);
                const title = panel.querySelector(".epc-panel-header span");
                if (title && !this._addingPeople) title.textContent = this.groupCallMode ? "Start group call" : "Calls";
            }
            if (modeBtn) {
                modeBtn.classList.toggle("epc-control-active", this.groupCallMode);
                const span = modeBtn.querySelector("span");
                if (span) span.textContent = this.groupCallMode ? "Cancel group" : "Group call";
            }
            if (actions) actions.classList.toggle("epc-hidden", !this.groupCallMode);
            this._updateGroupSelectionUI();
            this._renderContacts();
        }

        _updateGroupSelectionUI() {
            const count = document.getElementById("epc-group-count");
            const start = document.getElementById("epc-start-group");
            const n = this.groupSelection.size;
            if (count) count.textContent = `${n} selected`;
            if (start) start.disabled = n < 2;
        }

        _toggleGroupSelection(userId) {
            const uid = Number(userId);
            if (!uid) return;
            if (this.groupSelection.has(uid)) this.groupSelection.delete(uid);
            else this.groupSelection.add(uid);
            this._updateGroupSelectionUI();
            this._renderContacts();
        }

        _positionPanel(anchor) {
            const panel = document.getElementById("epc-panel");
            if (!anchor || !panel) return;
            const rect = anchor.getBoundingClientRect();
            const gap = 10;
            const edge = 12;
            if (this._addingPeople) {
                panel.style.left = "50%";
                panel.style.right = "auto";
                panel.style.width = "420px";
                panel.style.maxWidth = "calc(100vw - 32px)";
                panel.style.top = "50%";
                panel.style.bottom = "auto";
                panel.style.transform = "translate(-50%, -50%)";
                panel.style.maxHeight = `${Math.min(560, window.innerHeight - 48)}px`;
                return;
            }
            panel.style.transform = "none";
            panel.style.top = `${Math.max(edge, rect.bottom + gap)}px`;
            panel.style.bottom = "auto";
            if (window.innerWidth <= 768) {
                // On phones anchor the directory to the viewport, not to the icon.
                // This prevents the panel from being pushed outside the screen when
                // the call icon is close to either edge of the mobile header.
                panel.style.left = `${edge}px`;
                panel.style.right = `${edge}px`;
                panel.style.width = "auto";
                panel.style.maxWidth = "none";
            } else {
                panel.style.right = `${Math.max(edge, window.innerWidth - rect.right)}px`;
                panel.style.left = "auto";
                panel.style.width = "";
                panel.style.maxWidth = "";
            }
            const maxHeight = Math.max(220, window.innerHeight - rect.bottom - gap - edge);
            panel.style.maxHeight = `${Math.min(430, maxHeight)}px`;
        }

        _bindPresenceActivity() {
            const mark = () => { this._lastLocalActivity = Date.now(); };
            ['mousedown', 'keydown', 'touchstart', 'scroll'].forEach((eventName) => {
                window.addEventListener(eventName, mark, { passive: true });
            });
            window.addEventListener('mousemove', mark, { passive: true });
        }

        _startPresenceHeartbeat() {
            const beat = async () => {
                const active = (Date.now() - this._lastLocalActivity) < 60000;
                try {
                    const res = await rpc('/employee_portal/call/presence', { active });
                    const statuses = (res && res.statuses) || {};
                    if (this.contacts && this.contacts.length) {
                        this.contacts.forEach((contact) => {
                            contact.presence = statuses[String(contact.user_id)] || contact.presence || 'offline';
                        });
                        const panel = document.getElementById('epc-panel');
                        if (panel && !panel.classList.contains('epc-hidden')) this._renderContacts();
                    }
                } catch (e) {
                    // Presence is informational only and must never interrupt calls.
                }
                this.presenceTimer = setTimeout(beat, PRESENCE_INTERVAL_MS);
            };
            beat();
        }

        _presenceLabel(status) {
            return ({ online: 'Online', away: 'Away', offline: 'Offline', in_call: 'In call' })[status] || 'Offline';
        }

        async _loadContacts() {
            try {
                this.contacts = await rpc("/employee_portal/call/contacts", {});
            } catch (e) {
                this.contacts = [];
            }
            this._renderContacts();
        }

        _renderContacts() {
            const list = document.getElementById("epc-contact-list");
            const search = document.getElementById("epc-contact-search");
            const term = (search ? search.value : "").trim().toLowerCase();
            const contacts = this.contacts.filter((c) =>
                !term || (c.name || "").toLowerCase().includes(term) ||
                (c.user_type || "").toLowerCase().includes(term) ||
                (c.department || "").toLowerCase().includes(term) ||
                (c.note || "").toLowerCase().includes(term)
            );

            list.innerHTML = "";
            if (!contacts.length) {
                list.innerHTML = `<div class="epc-empty">${term ? "No matching employees." : "No other active employees found."}</div>`;
                return;
            }
            contacts.forEach((c) => {
                const row = document.createElement("div");
                row.className = "epc-contact-row";
                const identity = document.createElement("div");
                identity.className = "epc-contact-identity";
                const presence = c.presence || 'offline';
                const presenceLabel = this._presenceLabel(presence);
                identity.innerHTML = `<span class="epc-contact-photo-wrap"><img class="epc-contact-photo" src="${this._escape(c.avatar_url || "")}" alt="" onerror="this.style.display=\'none\'"/><span class="epc-contact-photo-fallback">${this._escape((c.name || "?").charAt(0).toUpperCase())}</span></span><span class="epc-contact-name">${this._escape(c.name)}</span><span class="epc-presence epc-presence-${this._escape(presence)}" title="${this._escape(presenceLabel)}"><span class="epc-presence-dot"></span><span class="epc-presence-label">${this._escape(presenceLabel)}</span></span>`;
                const callBtn = document.createElement("button");
                const adding = this.currentUuid && this._addingPeople;
                const groupSelecting = !adding && this.groupCallMode;
                const selected = groupSelecting && this.groupSelection.has(Number(c.user_id));
                if (groupSelecting) {
                    callBtn.innerHTML = selected ? '<i class="fa fa-check"></i>' : '<i class="fa fa-plus"></i>';
                    callBtn.title = selected ? "Remove from group call" : "Add to group call";
                    callBtn.className = "epc-btn epc-btn-small epc-contact-call-btn epc-group-select-btn" + (selected ? " epc-selected" : "");
                    row.classList.toggle("epc-contact-selected", selected);
                    callBtn.addEventListener("click", (ev) => {
                        ev.preventDefault();
                        ev.stopPropagation();
                        this._toggleGroupSelection(c.user_id);
                    });
                    row.addEventListener("click", (ev) => {
                        ev.preventDefault();
                        ev.stopPropagation();
                        if (!ev.target.closest("button")) this._toggleGroupSelection(c.user_id);
                    });
                } else {
                    callBtn.innerHTML = adding ? '<i class="fa fa-user-plus"></i><span>Add</span>' : '<i class="fa fa-phone"></i><span>Call</span>';
                    callBtn.title = adding ? "Add to meeting" : "Call";
                    callBtn.className = "epc-btn epc-btn-small epc-contact-call-btn";
                    callBtn.addEventListener("click", () => this.currentUuid && this._addingPeople ? this._addParticipant(c.user_id) : this._startCall(c.user_id));
                }
                row.appendChild(identity);
                row.appendChild(callBtn);
                list.appendChild(row);
            });
        }

        _escape(s) {
            const d = document.createElement("div");
            d.textContent = s || "";
            return d.innerHTML;
        }

        // ------------------------------------------------------------
        // Incoming-call alerts (ringtone + browser notification)
        // ------------------------------------------------------------
        async _unlockCallAlerts(requestNotification) {
            try {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx && !this.ringContext) {
                    this.ringContext = new AudioCtx();
                    this.ringGain = this.ringContext.createGain();
                    this.ringGain.gain.value = 0.0001;
                    this.ringGain.connect(this.ringContext.destination);
                }
                if (this.ringContext && this.ringContext.state === "suspended") {
                    await this.ringContext.resume();
                }
            } catch (e) {
                // Sound is optional; browser may block it until a later gesture.
            }
            if (requestNotification && "Notification" in window && Notification.permission === "default") {
                try {
                    await Notification.requestPermission();
                } catch (e) {
                    // Some browsers may reject permission requests in embedded contexts.
                }
            }
        }

        _startRinging() {
            this._stopRinging();
            if (!this.ringContext || this.ringContext.state !== "running" || !this.ringGain) return;
            const playBurst = () => {
                if (!this.currentUuid || document.getElementById("epc-incoming").classList.contains("epc-hidden")) return;
                try {
                    const now = this.ringContext.currentTime;
                    const osc1 = this.ringContext.createOscillator();
                    const osc2 = this.ringContext.createOscillator();
                    const gain = this.ringContext.createGain();
                    osc1.frequency.value = 440;
                    osc2.frequency.value = 480;
                    gain.gain.setValueAtTime(0.0001, now);
                    gain.gain.exponentialRampToValueAtTime(0.12, now + 0.03);
                    gain.gain.setValueAtTime(0.12, now + 0.55);
                    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.72);
                    osc1.connect(gain);
                    osc2.connect(gain);
                    gain.connect(this.ringGain);
                    this.ringGain.gain.value = 1.0;
                    osc1.start(now);
                    osc2.start(now);
                    osc1.stop(now + 0.75);
                    osc2.stop(now + 0.75);
                } catch (e) {
                    // Ignore audio-device failures.
                }
            };
            playBurst();
            this.ringTimer = setInterval(playBurst, 1800);
        }

        _stopRinging() {
            if (this.ringTimer) {
                clearInterval(this.ringTimer);
                this.ringTimer = null;
            }
            if (this.ringGain) this.ringGain.gain.value = 0.0001;
        }

        _notifyIncoming(name) {
            if (!("Notification" in window) || Notification.permission !== "granted") return;
            try {
                const notice = new Notification(`Incoming call from ${name || "Employee"}`, {
                    body: "Open Odoo to accept or decline the call.",
                    tag: `epc-${this.currentUuid || "incoming"}`,
                    renotify: true,
                    requireInteraction: true,
                });
                notice.onclick = () => {
                    window.focus();
                    notice.close();
                };
                this._activeNotification = notice;
            } catch (e) {
                // Native notifications are best-effort only.
            }
        }

        _closeNotification() {
            if (this._activeNotification) {
                try { this._activeNotification.close(); } catch (e) { /* no-op */ }
                this._activeNotification = null;
            }
        }

        _setPeerName(name) {
            this.currentPeerName = name || "Employee";
            const activeName = document.querySelector("#epc-active .epc-active-name");
            if (activeName) activeName.textContent = this.currentPeerName;
            const initial = document.getElementById("epc-peer-initial");
            if (initial) initial.textContent = (this.currentPeerName.trim().charAt(0) || "?").toUpperCase();
            const contact = this.contacts.find((c) => c.name === this.currentPeerName);
            const photo = document.getElementById("epc-peer-photo");
            if (photo) { if (contact && contact.avatar_url) { photo.src = contact.avatar_url; photo.classList.remove("epc-hidden"); if (initial) initial.classList.add("epc-hidden"); photo.onerror = () => { photo.classList.add("epc-hidden"); if (initial) initial.classList.remove("epc-hidden"); }; } else { photo.classList.add("epc-hidden"); if (initial) initial.classList.remove("epc-hidden"); } }
        }

        _startCallTimer() {
            this._stopCallTimer();
            this.callStartedAt = Date.now();
            const timer = document.querySelector("#epc-active .epc-call-timer");
            const tick = () => {
                if (!timer || !this.callStartedAt) return;
                const seconds = Math.max(0, Math.floor((Date.now() - this.callStartedAt) / 1000));
                const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
                const secs = String(seconds % 60).padStart(2, "0");
                timer.textContent = `${mins}:${secs}`;
            };
            tick();
            this.callTimer = setInterval(tick, 1000);
        }

        _stopCallTimer() {
            if (this.callTimer) clearInterval(this.callTimer);
            this.callTimer = null;
            this.callStartedAt = null;
            const timer = document.querySelector("#epc-active .epc-call-timer");
            if (timer) timer.textContent = "00:00";
        }

        // ------------------------------------------------------------
        // Network / WebRTC recovery
        // ------------------------------------------------------------
        _bindNetworkRecovery() {
            window.addEventListener("offline", () => {
                this._networkOffline = true;
                if (this.currentUuid) this._setCallStatus("Connection lost - waiting for network...");
            });
            window.addEventListener("online", () => {
                this._networkOffline = false;
                if (!this.currentUuid) return;
                this._setCallStatus("Reconnecting...");
                // A network change can leave a peer connection reporting
                // "connected" for a short time even though the old ICE path is
                // dead. Force an ICE restart for every current peer.
                setTimeout(() => this._retryDisconnectedPeers(true), 300);
            });
            document.addEventListener("visibilitychange", () => {
                if (document.visibilityState === "visible" && this.currentUuid && navigator.onLine) {
                    this._retryDisconnectedPeers(false);
                }
            });
        }

        _setCallStatus(text) {
            const status = document.querySelector("#epc-active .epc-active-status");
            if (status && this.currentUuid) status.textContent = text;
        }

        _restoreMeetingStatus() {
            if (!this.currentUuid) return;
            const activeCount = (this.participants || []).filter((p) => p.active).length;
            const count = activeCount || (this.peerConnections.size + 1);
            this._setCallStatus(`${Math.max(1, count)} people in meeting`);
        }

        _clearReconnectTimer(peerId, resetAttempts=false) {
            peerId = Number(peerId);
            const timer = this.reconnectTimers.get(peerId);
            if (timer) clearTimeout(timer);
            this.reconnectTimers.delete(peerId);
            if (resetAttempts) this.reconnectAttempts.delete(peerId);
        }

        _scheduleReconnect(peerId, immediate=false) {
            peerId = Number(peerId);
            if (!this.currentUuid || !peerId) return;
            const pc = this.peerConnections.get(peerId);
            if (!pc || pc.signalingState === "closed") return;
            this._clearReconnectTimer(peerId, false);
            this.peerConnectionStates.set(peerId, "reconnecting");
            this._setCallStatus(this._networkOffline ? "Connection lost - waiting for network..." : "Reconnecting...");

            // Avoid both sides creating restart offers at the same instant. The
            // lower user id takes the first attempt; the other side is a delayed
            // fallback in case the preferred peer is the one that lost network.
            const preferredInitiator = !this.selfUserId || this.selfUserId < peerId;
            const attempt = this.reconnectAttempts.get(peerId) || 0;
            let delay = immediate ? 250 : (preferredInitiator ? 1200 : 5000);
            if (attempt > 0) delay = Math.min(10000, delay + (attempt * 1500));
            const timer = setTimeout(() => this._restartIceTo(peerId), delay);
            this.reconnectTimers.set(peerId, timer);
        }

        async _restartIceTo(peerId) {
            peerId = Number(peerId);
            this.reconnectTimers.delete(peerId);
            if (!this.currentUuid || !navigator.onLine) {
                if (this.currentUuid) this._scheduleReconnect(peerId, false);
                return;
            }
            const pc = this.peerConnections.get(peerId);
            if (!pc || pc.signalingState === "closed") return;

            const attempts = (this.reconnectAttempts.get(peerId) || 0) + 1;
            this.reconnectAttempts.set(peerId, attempts);
            this._setCallStatus(`Reconnecting...${attempts > 1 ? ` (${attempts})` : ""}`);
            try {
                if (typeof pc.restartIce === "function") pc.restartIce();
                // Do not stack an ICE restart on top of an SDP exchange already
                // in progress. A received offer will itself carry fresh ICE.
                if (pc.signalingState !== "stable") {
                    this._scheduleReconnect(peerId, false);
                    return;
                }
                const offer = await pc.createOffer({ iceRestart: true });
                await pc.setLocalDescription(offer);
                await rpc("/employee_portal/call/signal", {
                    uuid: this.currentUuid,
                    signal_type: "offer",
                    data: {
                        type: offer.type,
                        sdp: offer.sdp,
                        _target_user_id: peerId,
                        _ice_restart: true,
                    },
                });
                // If the state never returns to connected, try again with
                // backoff. Successful connection clears this timer below.
                this._clearReconnectTimer(peerId, false);
                const watchdog = setTimeout(() => {
                    const current = this.peerConnections.get(peerId);
                    if (current && !["connected", "closed"].includes(current.connectionState)) {
                        this._scheduleReconnect(peerId, false);
                    }
                }, 6500);
                this.reconnectTimers.set(peerId, watchdog);
            } catch (e) {
                console.warn("[EPC] ICE restart failed", peerId, e);
                this._scheduleReconnect(peerId, false);
            }
        }

        _handlePeerConnectionState(peerId, pc) {
            if (!this.currentUuid || !pc) return;
            const state = pc.connectionState || pc.iceConnectionState || "new";
            const previous = this.peerConnectionStates.get(Number(peerId));
            if (state === "connected" || state === "completed") {
                this._clearReconnectTimer(peerId, true);
                this.peerConnectionStates.set(Number(peerId), "connected");
                if (previous === "reconnecting" || previous === "disconnected" || previous === "failed") {
                    this._setCallStatus("Connected");
                    setTimeout(() => {
                        if (this.currentUuid && !Array.from(this.peerConnectionStates.values()).some((v) => ["reconnecting", "disconnected", "failed"].includes(v))) {
                            this._restoreMeetingStatus();
                        }
                    }, 1200);
                } else {
                    this._restoreMeetingStatus();
                }
            } else if (state === "disconnected") {
                this.peerConnectionStates.set(Number(peerId), "disconnected");
                this._scheduleReconnect(peerId, false);
            } else if (state === "failed") {
                this.peerConnectionStates.set(Number(peerId), "failed");
                this._scheduleReconnect(peerId, true);
            }
        }

        _retryDisconnectedPeers(force=false) {
            if (!this.currentUuid || !navigator.onLine) return;
            for (const [peerId, pc] of this.peerConnections.entries()) {
                if (!pc || pc.signalingState === "closed") continue;
                const state = pc.connectionState || pc.iceConnectionState || "new";
                if (force || ["disconnected", "failed"].includes(state)) {
                    this._scheduleReconnect(peerId, force);
                }
            }
        }

        // ------------------------------------------------------------
        // Polling loop
        // ------------------------------------------------------------
        _startPolling() {
            const tick = async () => {
                try {
                    const res = await rpc("/employee_portal/call/poll", { last_id: this.lastId });
                    this.lastId = res.last_id;
                    for (const evt of res.events) {
                        await this._handleEvent(evt);
                    }
                } catch (e) {
                    // network hiccup / session expiry: keep polling silently
                }
                this.pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
            };
            tick();
        }

        async _handleEvent(evt) {
            if (evt.event === "incoming") {
                this.currentUuid = evt.uuid;
                this.currentCallType = evt.payload.call_type || "audio";
                this._incomingCallerId = Number(evt.payload.caller_id || 0);
                const callerName = evt.payload.caller_name || "Unknown";
                this.peerNames.set(this._incomingCallerId, callerName);
                this._setPeerName(callerName);
                document.querySelector("#epc-incoming .epc-incoming-name").textContent = callerName;
                const incomingPhoto = document.getElementById("epc-incoming-photo");
                const incomingFallback = document.getElementById("epc-incoming-fallback");
                if (incomingPhoto && evt.payload.caller_avatar_url) { incomingPhoto.src = evt.payload.caller_avatar_url; incomingPhoto.classList.remove("epc-hidden"); if (incomingFallback) incomingFallback.classList.add("epc-hidden"); incomingPhoto.onerror = () => { incomingPhoto.classList.add("epc-hidden"); if (incomingFallback) incomingFallback.classList.remove("epc-hidden"); }; }
                document.querySelector("#epc-incoming .epc-incoming-sub").textContent = evt.payload.meeting ? "Meeting invitation" : (this.currentCallType === "video" ? "Incoming video call" : "Incoming audio call");
                document.getElementById("epc-incoming").classList.remove("epc-hidden");
                this._startRinging(); this._notifyIncoming(callerName);
            } else if (evt.event === "signal" && evt.uuid === this.currentUuid) {
                await this._handleSignal(evt.payload);
            } else if (evt.event === "accepted" && evt.uuid === this.currentUuid) {
                const uid = Number(evt.payload.user_id || 0);
                if (uid) {
                    this.peerNames.set(uid, evt.payload.user_name || "Employee");
                    await this._createOfferTo(uid);
                }
                document.querySelector("#epc-active .epc-active-status").textContent = "Meeting connected";
                this._startCallTimer();
                await this._refreshParticipants();
            } else if (evt.event === "participant_left" && evt.uuid === this.currentUuid) {
                this._removePeer(Number(evt.payload.user_id || 0));
                await this._refreshParticipants();
            } else if (["rejected", "ended", "cancelled"].includes(evt.event) && evt.uuid === this.currentUuid) {
                // A remote decline/cancel/end must also dismiss a still-ringing
                // incoming call. Previously cancelled/rejected only refreshed
                // history, leaving the recipient popup visible until Decline.
                this._stopRinging();
                this._closeNotification();
                const incoming = document.getElementById("epc-incoming");
                if (incoming) incoming.classList.add("epc-hidden");
                this._teardown();
                setTimeout(() => this._refreshCallHistory(), 300);
            }
        }

        // ------------------------------------------------------------
        // Call actions
        // ------------------------------------------------------------
        async _startCall(targetUserId) {
            try {
                const res = await rpc("/employee_portal/call/start", {
                    target_user_id: targetUserId,
                    call_type: "audio",
                });
                if (res.error) {
                    alert("Could not start call: " + res.error);
                    return;
                }
                this.currentUuid = res.uuid;
                this._iAmCaller = true;
                const contact = this.contacts.find((c) => Number(c.user_id) === Number(targetUserId));
                this._setPeerName(contact ? contact.name : "Employee");
                document.getElementById("epc-panel").classList.add("epc-hidden");
                await this._prepareLocalMedia();
                this._showActive("Calling…");
            } catch (e) {
                alert("Could not start call.");
            }
        }

        async _startGroupCall() {
            const userIds = Array.from(this.groupSelection);
            if (userIds.length < 2) return;
            try {
                const res = await rpc("/employee_portal/call/start", {
                    target_user_ids: userIds,
                    call_type: "audio",
                });
                if (res.error) {
                    alert("Could not start group call: " + res.error);
                    return;
                }
                this.currentUuid = res.uuid;
                this._iAmCaller = true;
                this.currentPeerName = "Group call";
                this._setPeerName("Group call");
                this.groupSelection.clear();
                this.groupCallMode = false;
                this._closeContactPanel();
                await this._prepareLocalMedia();
                this._showActive(`Calling ${userIds.length} employees…`);
                await this._refreshParticipants();
            } catch (e) {
                console.error("[EPC] Could not start group call", e);
                alert("Could not start group call.");
            }
        }

        async _addParticipant(userId) {
            if (!this.currentUuid) return;
            const res = await rpc("/employee_portal/call/add_participants", {uuid: this.currentUuid, user_ids: [userId]});
            if (res && res.added && res.added.length) {
                const c = this.contacts.find(x => Number(x.user_id) === Number(userId));
                if (c) this.peerNames.set(Number(userId), c.name);
                document.querySelector("#epc-active .epc-active-status").textContent = `Invited ${c ? c.name : "employee"}…`;
                await this._refreshParticipants();
            }
            this._closeContactPanel();
        }

        async _acceptIncoming() {
            if (!this.currentUuid) return;
            this._stopRinging();
            this._closeNotification();
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this._iAmCaller = false;
            await this._prepareLocalMedia();
            this._showActive("Joining meeting…");
            this._startCallTimer();
            await rpc("/employee_portal/call/accept", { uuid: this.currentUuid });
            await this._refreshParticipants();
        }

        async _rejectIncoming() {
            if (!this.currentUuid) return;
            this._stopRinging();
            this._closeNotification();
            await rpc("/employee_portal/call/reject", { uuid: this.currentUuid });
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
            setTimeout(() => this._refreshCallHistory(), 300);
        }

        async _hangup() {
            if (this.currentUuid) {
                await rpc("/employee_portal/call/end", { uuid: this.currentUuid });
            }
            this._teardown();
            setTimeout(() => this._refreshCallHistory(), 300);
        }

        _toggleMute() {
            if (!this.localStream) return;
            const tracks = this.localStream.getAudioTracks();
            if (!tracks.length) return;
            const willMute = tracks.some((t) => t.enabled);
            tracks.forEach((t) => (t.enabled = !willMute));
            const btn = document.getElementById("epc-mute");
            if (btn) {
                btn.classList.toggle("epc-control-active", willMute);
                btn.querySelector("i").className = willMute ? "fa fa-microphone-slash" : "fa fa-microphone";
                const label = btn.querySelector("span");
                if (label) label.textContent = willMute ? "Unmute" : "Mute";
            }
        }


        async _toggleSpeaker() {
            const btn = document.getElementById("epc-speaker");
            if (!btn) return;

            // Keep the control visible on mobile even when the browser cannot
            // programmatically route audio. Capability affects behavior, not UI.
            const mediaEls = Array.from(document.querySelectorAll("#epc-active audio, #epc-active video"));
            const canRoute = mediaEls.some((el) => typeof el.setSinkId === "function");
            if (!canRoute || !navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
                alert("This phone browser does not allow Odoo to switch between earpiece and speaker. Use the phone/browser audio controls instead.");
                return;
            }

            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                const outputs = devices.filter((d) => d.kind === "audiooutput");
                if (!outputs.length) {
                    alert("No selectable audio outputs were exposed by this phone browser.");
                    return;
                }

                if (!this.defaultSinkId) {
                    const def = outputs.find((d) => d.deviceId === "default") || outputs[0];
                    this.defaultSinkId = def.deviceId;
                }
                if (!this.speakerSinkId) {
                    const speaker = outputs.find((d) => /speaker|loudspeaker/i.test(d.label || ""));
                    this.speakerSinkId = speaker ? speaker.deviceId : null;
                }

                if (!this.speakerEnabled && !this.speakerSinkId) {
                    alert("Your phone exposes audio output control, but it does not expose a separate loudspeaker device to the browser.");
                    return;
                }

                const targetSink = this.speakerEnabled ? this.defaultSinkId : this.speakerSinkId;
                for (const el of mediaEls) {
                    if (typeof el.setSinkId === "function") {
                        await el.setSinkId(targetSink);
                    }
                }
                this.speakerEnabled = !this.speakerEnabled;
                btn.classList.toggle("epc-control-active", this.speakerEnabled);
                const label = btn.querySelector("span");
                if (label) label.textContent = this.speakerEnabled ? "Speaker on" : "Speaker";
            } catch (e) {
                console.warn("[EPC] Speaker routing unavailable", e);
                alert("This phone/browser did not allow Odoo to change the audio output.");
            }
        }

        _isDesktopScreenShareSupported() {
            return window.innerWidth > 768 &&
                !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);
        }

        _updateScreenShareAvailability() {
            const btn = document.getElementById("epc-share-screen");
            if (!btn) return;
            const supported = this._isDesktopScreenShareSupported();
            btn.classList.toggle("epc-hidden", !supported);
            btn.disabled = !supported;
        }

        async _toggleScreenShare() {
            if (this.screenTrack) {
                await this._stopScreenShare();
            } else {
                await this._startScreenShare();
            }
        }

        async _startScreenShare() {
            if (!this.currentUuid || !this._isDesktopScreenShareSupported()) return;
            try {
                this.screenStream = await navigator.mediaDevices.getDisplayMedia({
                    video: true,
                    audio: false,
                });
                this.screenTrack = this.screenStream.getVideoTracks()[0];
                if (!this.screenTrack) return;

                const shareTrack = this.screenTrack;

                // Show the shared display to the person who is sharing as well.
                // The main stage is muted locally so the preview can never echo audio.
                const localSharePreview = document.getElementById("epc-remote-video");
                const localShareStage = document.querySelector("#epc-active .epc-video-stage");
                if (localSharePreview) {
                    localSharePreview.muted = true;
                    localSharePreview.srcObject = this.screenStream;
                    try { await localSharePreview.play(); } catch (e) { /* autoplay can be browser-controlled */ }
                }
                if (localShareStage) localShareStage.classList.remove("epc-hidden");

                const renegotiate = [];
                for (const [peerId, pc] of this.peerConnections.entries()) {
                    const videoSender = pc.getSenders().find((sender) => sender.track && sender.track.kind === "video");
                    if (videoSender) {
                        if (!this._cameraTrackBeforeShare) this._cameraTrackBeforeShare = videoSender.track;
                        await videoSender.replaceTrack(shareTrack);
                    } else {
                        pc.addTrack(shareTrack, this.screenStream);
                        renegotiate.push(peerId);
                    }
                }

                // Audio-only meetings need a fresh SDP offer because screen video
                // adds a new transceiver. Existing video calls can use replaceTrack.
                for (const peerId of renegotiate) {
                    await this._renegotiatePeer(peerId);
                }

                shareTrack.addEventListener("ended", () => {
                    if (this.screenTrack === shareTrack) this._stopScreenShare();
                }, { once: true });

                const btn = document.getElementById("epc-share-screen");
                if (btn) {
                    btn.classList.add("epc-control-active");
                    btn.querySelector("i").className = "fa fa-stop-circle";
                    const label = btn.querySelector("span");
                    if (label) label.textContent = "Stop sharing";
                }
                const status = document.querySelector("#epc-active .epc-active-status");
                if (status) status.textContent = "You are sharing your screen";
            } catch (e) {
                // User cancelling the browser picker is normal; do not show an error.
                if (e && e.name !== "NotAllowedError" && e.name !== "AbortError") {
                    console.error("[EPC] Screen share failed", e);
                    alert("Could not start screen sharing.");
                }
            }
        }

        async _stopScreenShare() {
            const oldTrack = this.screenTrack;
            if (!oldTrack) return;
            this.screenTrack = null;

            const renegotiate = [];
            for (const [peerId, pc] of this.peerConnections.entries()) {
                const sender = pc.getSenders().find((item) => item.track === oldTrack);
                if (!sender) continue;
                if (this.currentCallType === "video" && this._cameraTrackBeforeShare) {
                    await sender.replaceTrack(this._cameraTrackBeforeShare);
                } else {
                    try { pc.removeTrack(sender); } catch (e) { /* no-op */ }
                    renegotiate.push(peerId);
                }
            }

            try { oldTrack.stop(); } catch (e) { /* no-op */ }
            if (this.screenStream) {
                this.screenStream.getTracks().forEach((track) => {
                    if (track !== oldTrack) {
                        try { track.stop(); } catch (e) { /* no-op */ }
                    }
                });
            }
            this.screenStream = null;
            this._cameraTrackBeforeShare = null;

            // Clear the sharer's own preview immediately. Without this, the video
            // element keeps rendering the final captured frame after the display
            // track has ended.
            const localSharePreview = document.getElementById("epc-remote-video");
            const localShareStage = document.querySelector("#epc-active .epc-video-stage");
            if (localSharePreview && localSharePreview.srcObject) {
                try { localSharePreview.pause(); } catch (e) { /* no-op */ }
                localSharePreview.srcObject = null;
                localSharePreview.muted = false;
                try { localSharePreview.removeAttribute("src"); localSharePreview.load(); } catch (e) { /* no-op */ }
            }
            if (this.currentCallType !== "video" && localShareStage) localShareStage.classList.add("epc-hidden");

            // Explicitly notify all peers that screen sharing ended. Removing a
            // WebRTC sender/renegotiating does not consistently fire `ended` on
            // every browser, which is why remote clients could retain a frozen
            // final frame.
            try {
                await rpc("/employee_portal/call/signal", {
                    uuid: this.currentUuid,
                    signal_type: "screen_stopped",
                    data: {},
                });
            } catch (e) { /* best effort; SDP renegotiation still follows */ }

            for (const peerId of renegotiate) {
                await this._renegotiatePeer(peerId);
            }

            const btn = document.getElementById("epc-share-screen");
            if (btn) {
                btn.classList.remove("epc-control-active");
                btn.querySelector("i").className = "fa fa-desktop";
                const label = btn.querySelector("span");
                if (label) label.textContent = "Share screen";
            }
            const status = document.querySelector("#epc-active .epc-active-status");
            if (status && this.currentUuid) status.textContent = `${this.peerConnections.size + 1} people in meeting`;
        }

        async _renegotiatePeer(peerId) {
            const pc = this.peerConnections.get(Number(peerId));
            if (!pc || pc.signalingState === "closed") return;
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            await rpc("/employee_portal/call/signal", {
                uuid: this.currentUuid,
                signal_type: "offer",
                data: { type: offer.type, sdp: offer.sdp, _target_user_id: Number(peerId) },
            });
        }

        _showActive(status) {
            const active = document.getElementById("epc-active");
            active.classList.remove("epc-hidden");
            active.classList.toggle("epc-video-call", this.currentCallType === "video");
            active.classList.toggle("epc-audio-call", this.currentCallType !== "video");
            const videoStage = active.querySelector(".epc-video-stage");
            const audioStage = active.querySelector(".epc-active-stage");
            if (videoStage) videoStage.classList.toggle("epc-hidden", this.currentCallType !== "video");
            if (audioStage) audioStage.classList.toggle("epc-video-name-overlay", this.currentCallType === "video");
            this._setPeerName(this.currentPeerName);
            document.querySelector("#epc-active .epc-active-status").textContent = status;
            this._refreshParticipants().catch(() => {});
        }

        _teardown() {
            this._stopRinging();
            this._closeNotification();
            this._stopCallTimer();
            for (const timer of this.reconnectTimers.values()) clearTimeout(timer);
            this.reconnectTimers = new Map();
            this.reconnectAttempts = new Map();
            this.peerConnectionStates = new Map();
            for (const pc of this.peerConnections.values()) {
                try { pc.close(); } catch (e) { /* no-op */ }
            }
            this.pc = null; // legacy alias for first peer
            this.peerConnections = new Map();
            this.peerNames = new Map();
            this.selfUserId = null;
            if (this.screenTrack) {
                try { this.screenTrack.stop(); } catch (e) { /* no-op */ }
                this.screenTrack = null;
            }
            if (this.screenStream) {
                this.screenStream.getTracks().forEach((t) => { try { t.stop(); } catch (e) { /* no-op */ } });
                this.screenStream = null;
            }
            this._cameraTrackBeforeShare = null;
            this.speakerEnabled = false;
            const speakerBtn = document.getElementById("epc-speaker");
            if (speakerBtn) {
                speakerBtn.classList.remove("epc-control-active");
                const speakerLabel = speakerBtn.querySelector("span");
                if (speakerLabel) speakerLabel.textContent = "Speaker";
            }
            const remoteVideo = document.getElementById("epc-remote-video");
            const videoStage = document.querySelector("#epc-active .epc-video-stage");
            if (remoteVideo) {
                try { remoteVideo.pause(); } catch (e) { /* no-op */ }
                remoteVideo.srcObject = null;
                remoteVideo.muted = false;
                try { remoteVideo.removeAttribute("src"); remoteVideo.load(); } catch (e) { /* no-op */ }
            }
            if (videoStage) videoStage.classList.add("epc-hidden");

            const shareBtn = document.getElementById("epc-share-screen");
            if (shareBtn) {
                shareBtn.classList.remove("epc-control-active");
                shareBtn.querySelector("i").className = "fa fa-desktop";
                const label = shareBtn.querySelector("span");
                if (label) label.textContent = "Share screen";
            }
            if (this.localStream) {
                this.localStream.getTracks().forEach((t) => t.stop());
                this.localStream = null;
            }
            const localVideo = document.getElementById("epc-local-video");
            if (localVideo) localVideo.srcObject = null;
            document.getElementById("epc-active").classList.add("epc-hidden");
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
            this.currentPeerName = "";
            this.pendingIceCandidates = new Map();
            this.participants = [];
            this._renderParticipants();
        }

        async _refreshParticipants() {
            if (!this.currentUuid) return;
            try {
                const res = await rpc("/employee_portal/call/participants", { uuid: this.currentUuid });
                if (res && Array.isArray(res.participants)) {
                    this.participants = res.participants;
                    res.participants.forEach((p) => {
                        if (p.is_self && p.user_id) this.selfUserId = Number(p.user_id);
                        if (!p.is_self && p.user_id && p.name) this.peerNames.set(Number(p.user_id), p.name);
                    });
                    this._renderParticipants();
                }
            } catch (e) {
                console.warn("[EPC] Could not refresh participants", e);
            }
        }

        _renderParticipants() {
            const list = document.getElementById("epc-participant-list");
            const count = document.getElementById("epc-participant-count");
            if (!list || !count) return;
            const active = (this.participants || []).filter((p) => p.active);
            count.textContent = String(active.length || (this.currentUuid ? 1 : 0));
            list.innerHTML = "";
            active.forEach((p) => {
                const row = document.createElement("div");
                row.className = "epc-participant-chip";
                const initial = (p.name || "?").trim().charAt(0).toUpperCase() || "?";
                row.innerHTML = `<span class="epc-participant-avatar"><img src="${this._escape(p.avatar_url || "")}" alt="" onerror="this.style.display=\'none\'"/><span>${initial}</span></span><span class="epc-participant-name"></span>${p.is_self ? '<span class="epc-you-badge">You</span>' : ''}`;
                row.querySelector(".epc-participant-name").textContent = p.name || "Employee";
                list.appendChild(row);
            });
            if (!active.length && this.currentUuid) {
                list.innerHTML = '<div class="epc-participant-chip"><span class="epc-participant-avatar">Y</span><span class="epc-participant-name">You</span></div>';
            }
        }

        async _toggleFullscreen() {
            const stage = document.querySelector("#epc-active .epc-video-stage");
            if (!stage || stage.classList.contains("epc-hidden")) return;
            try {
                if (document.fullscreenElement || document.webkitFullscreenElement) {
                    if (document.exitFullscreen) await document.exitFullscreen();
                    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
                    return;
                }
                if (stage.requestFullscreen) await stage.requestFullscreen();
                else if (stage.webkitRequestFullscreen) stage.webkitRequestFullscreen();
            } catch (e) {
                console.warn("[EPC] Fullscreen was not available", e);
            }
        }

        _queueIceCandidate(peerId, candidate) {
            peerId = Number(peerId);
            if (!this.pendingIceCandidates.has(peerId)) this.pendingIceCandidates.set(peerId, []);
            this.pendingIceCandidates.get(peerId).push(candidate);
        }

        async _flushIceCandidates(peerId, pc) {
            peerId = Number(peerId);
            const queued = this.pendingIceCandidates.get(peerId) || [];
            if (!queued.length || !pc.remoteDescription) return;
            this.pendingIceCandidates.delete(peerId);
            for (const candidate of queued) {
                try { await pc.addIceCandidate(new RTCIceCandidate(candidate)); } catch (e) { console.warn("[EPC] ICE candidate rejected", e); }
            }
        }

        // ------------------------------------------------------------
        // WebRTC
        // ------------------------------------------------------------
        async _prepareLocalMedia() {
            try {
                this.localStream = await navigator.mediaDevices.getUserMedia({
                    audio: true,
                    video: this.currentCallType === "video",
                });
                document.getElementById("epc-local-video").srcObject = this.localStream;
            } catch (e) {
                alert("Microphone/camera access is required to make a call.");
                throw e;
            }
        }

        async _getIceServers() {
            try { const res = await rpc("/employee_portal/call/ice_servers", {}); this.iceServers = res.iceServers || this.iceServers; } catch (e) {}
        }

        async _createPeerConnection(peerId) {
            peerId = Number(peerId);
            if (this.peerConnections.has(peerId)) return this.peerConnections.get(peerId);
            await this._getIceServers();
            const pc = new RTCPeerConnection({ iceServers: this.iceServers });
            this.peerConnections.set(peerId, pc);
            if (!this.pc) this.pc = pc;
            this.localStream.getTracks().forEach((t) => pc.addTrack(t, this.localStream));
            if (this.screenTrack && this.currentCallType !== "video") {
                pc.addTrack(this.screenTrack, this.screenStream);
            } else if (this.screenTrack && this.currentCallType === "video") {
                const videoSender = pc.getSenders().find((sender) => sender.track && sender.track.kind === "video");
                if (videoSender) {
                    if (!this._cameraTrackBeforeShare) this._cameraTrackBeforeShare = videoSender.track;
                    await videoSender.replaceTrack(this.screenTrack);
                }
            }
            pc.ontrack = (ev) => {
                if (ev.track && ev.track.kind === "video") {
                    const remoteVideo = document.getElementById("epc-remote-video");
                    const stage = document.querySelector("#epc-active .epc-video-stage");
                    if (remoteVideo) remoteVideo.srcObject = ev.streams[0];
                    if (stage) stage.classList.remove("epc-hidden");
                    if (ev.track) {
                        ev.track.addEventListener("ended", () => {
                            if (this.currentCallType !== "video" && stage) stage.classList.add("epc-hidden");
                        }, { once: true });
                    }
                } else {
                    let audio = document.getElementById(`epc-remote-${peerId}`);
                    if (!audio) { audio = document.createElement("audio"); audio.id = `epc-remote-${peerId}`; audio.autoplay = true; audio.style.display = "none"; document.getElementById("epc-active").appendChild(audio); }
                    audio.srcObject = ev.streams[0];
                    if (this.speakerEnabled && this.speakerSinkId && typeof audio.setSinkId === "function") {
                        audio.setSinkId(this.speakerSinkId).catch(() => {});
                    }
                }
                const status = document.querySelector("#epc-active .epc-active-status");
                if (status) status.textContent = `${this.peerConnections.size + 1} people in meeting`;
                if (!this.callStartedAt) this._startCallTimer();
            };
            pc.onicecandidate = (ev) => { if (ev.candidate) rpc("/employee_portal/call/signal", {uuid:this.currentUuid, signal_type:"ice", data:{...ev.candidate.toJSON(), _target_user_id:peerId}}); };
            pc.onconnectionstatechange = () => this._handlePeerConnectionState(peerId, pc);
            pc.oniceconnectionstatechange = () => {
                // Some Safari/WebKit versions expose useful failure state here
                // before connectionState changes. Feed both into one recovery path.
                if (["disconnected", "failed", "connected", "completed"].includes(pc.iceConnectionState)) {
                    this._handlePeerConnectionState(peerId, pc);
                }
            };
            return pc;
        }

        async _createOfferTo(peerId) {
            if (!peerId) return;
            if (!this.localStream) await this._prepareLocalMedia();
            const pc = await this._createPeerConnection(peerId);
            const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
            await rpc("/employee_portal/call/signal", {uuid:this.currentUuid, signal_type:"offer", data:{type:offer.type, sdp:offer.sdp, _target_user_id:peerId}});
        }

        async _handleSignal(payload) {
            if (!payload) return;
            const peerId = Number(payload.sender_id || 0);
            if (!peerId) return;
            if (payload.sender_name) this.peerNames.set(peerId, payload.sender_name);
            const { signal_type, data } = payload;
            const pc = await this._createPeerConnection(peerId);
            if (signal_type === "offer") {
                // A reconnect offer can cross a normal renegotiation. Roll back
                // our uncommitted local offer so the remote restart offer wins.
                this._clearReconnectTimer(peerId, false);
                if (pc.signalingState !== "stable") {
                    try { await pc.setLocalDescription({ type: "rollback" }); } catch (e) { /* browser may already be stable */ }
                }
                await pc.setRemoteDescription(new RTCSessionDescription(data));
                await this._flushIceCandidates(peerId, pc);
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                await rpc("/employee_portal/call/signal", {uuid:this.currentUuid, signal_type:"answer", data:{type:answer.type, sdp:answer.sdp, _target_user_id:peerId}});
            } else if (signal_type === "answer") {
                if (pc.signalingState === "have-local-offer") {
                    await pc.setRemoteDescription(new RTCSessionDescription(data));
                    await this._flushIceCandidates(peerId, pc);
                }
            } else if (signal_type === "ice") {
                if (!pc.remoteDescription || !pc.remoteDescription.type) {
                    this._queueIceCandidate(peerId, data);
                } else {
                    try { await pc.addIceCandidate(new RTCIceCandidate(data)); } catch (e) {
                        this._queueIceCandidate(peerId, data);
                    }
                }
            } else if (signal_type === "screen_stopped") {
                // Browsers do not all emit a remote track `ended` event when a
                // sender removes a screen track. Clear the stage explicitly so a
                // stale screenshot cannot remain visible after sharing stops.
                if (this.currentCallType !== "video") {
                    const remoteVideo = document.getElementById("epc-remote-video");
                    const stage = document.querySelector("#epc-active .epc-video-stage");
                    if (remoteVideo) {
                        try { remoteVideo.pause(); } catch (e) { /* no-op */ }
                        remoteVideo.srcObject = null;
                        remoteVideo.muted = false;
                        try { remoteVideo.removeAttribute("src"); remoteVideo.load(); } catch (e) { /* no-op */ }
                    }
                    if (stage) stage.classList.add("epc-hidden");
                }
            }
        }

        _removePeer(peerId) {
            this._clearReconnectTimer(peerId, true);
            this.peerConnectionStates.delete(Number(peerId));
            const pc = this.peerConnections.get(peerId); if (pc) pc.close();
            this.peerConnections.delete(peerId);
            this.pendingIceCandidates.delete(Number(peerId));
            const audio = document.getElementById(`epc-remote-${peerId}`); if (audio) audio.remove();
            const status = document.querySelector("#epc-active .epc-active-status");
            if (status && this.currentUuid) status.textContent = `${this.peerConnections.size + 1} people in meeting`;
        }
    }

    function shouldMount() {
        // Backend: web client wrapper is always present for logged-in internal users.
        if (document.querySelector(".o_web_client")) {
            return true;
        }
        // Frontend/portal: only mount on actual portal pages for logged-in portal
        // users, never on public/anonymous website pages.
        const isPortalPage = document.body.classList.contains("o_portal") ||
            !!document.getElementById("epc-mount-marker");
        const isLoggedIn = document.body.getAttribute("data-epc-logged-in") === "1" ||
            !!document.getElementById("epc-mount-marker");
        return isPortalPage && isLoggedIn;
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (shouldMount()) {
            window.__employeePortalCaller = new EmployeePortalCaller();
        }
    });
})();
