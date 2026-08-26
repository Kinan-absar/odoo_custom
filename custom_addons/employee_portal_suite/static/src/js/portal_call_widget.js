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
            this._buildUI();
            this._loadContacts();
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
                <div id="epc-panel" class="epc-hidden">
                    <div class="epc-panel-header">
                        <span>Call an employee</span>
                        <button id="epc-panel-close">&times;</button>
                    </div>
                    <div class="epc-search-wrap"><input id="epc-contact-search" type="search" placeholder="Search employees…" autocomplete="off"/></div>
                    <div id="epc-contact-list"><div class="epc-empty">Loading…</div></div>
                </div>
                <div id="epc-incoming" class="epc-hidden">
                    <div class="epc-call-avatar epc-incoming-avatar"><i class="fa fa-phone"></i></div>
                    <div class="epc-incoming-name"></div>
                    <div class="epc-incoming-sub">Incoming audio call</div>
                    <div class="epc-incoming-actions">
                        <button id="epc-reject" class="epc-call-action epc-call-action-decline" title="Decline"><i class="fa fa-phone"></i><span>Decline</span></button>
                        <button id="epc-accept" class="epc-call-action epc-call-action-accept" title="Accept"><i class="fa fa-phone"></i><span>Accept</span></button>
                    </div>
                </div>
                <div id="epc-active" class="epc-hidden epc-audio-call">
                    <div class="epc-active-stage">
                        <div class="epc-call-avatar epc-active-avatar"><span id="epc-peer-initial">?</span></div>
                        <div class="epc-active-name">Employee</div>
                        <div class="epc-active-status">Connecting…</div>
                        <div class="epc-call-timer">00:00</div>
                    </div>
                    <div class="epc-video-stage epc-hidden">
                        <video id="epc-remote-video" autoplay playsinline></video>
                        <video id="epc-local-video" autoplay playsinline muted></video>
                    </div>
                    <div class="epc-active-actions">
                        <button id="epc-mute" class="epc-round-control" title="Mute"><i class="fa fa-microphone"></i><span>Mute</span></button>
                        <button id="epc-add-people" class="epc-round-control" title="Add people"><i class="fa fa-user-plus"></i><span>Add people</span></button>
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
            document.getElementById("epc-panel-close").addEventListener("click", () => {
                document.getElementById("epc-panel").classList.add("epc-hidden");
            });
            document.getElementById("epc-accept").addEventListener("click", () => this._acceptIncoming());
            document.getElementById("epc-reject").addEventListener("click", () => this._rejectIncoming());
            document.getElementById("epc-hangup").addEventListener("click", () => this._hangup());
            document.getElementById("epc-mute").addEventListener("click", () => this._toggleMute());
            document.getElementById("epc-add-people").addEventListener("click", () => {
                this._addingPeople = true;
                const panel = document.getElementById("epc-panel");
                panel.querySelector(".epc-panel-header span").textContent = "Add people to meeting";
                panel.classList.remove("epc-hidden");
                this._renderContacts();
            });
            document.getElementById("epc-contact-search").addEventListener("input", () => this._renderContacts());

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
                    panel.classList.add("epc-hidden");
                }
            });
            window.addEventListener("resize", () => {
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
            btn.innerHTML = '<i class="fa fa-phone"></i>';
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
            btn.innerHTML = '<i class="fa fa-phone"></i>';
            item.appendChild(btn);
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
                this._panelAnchor = anchor;
                panel.classList.remove("epc-hidden");
                this._positionPanel(anchor);
                const search = document.getElementById("epc-contact-search");
                if (search) setTimeout(() => search.focus(), 0);
            } else {
                panel.classList.add("epc-hidden");
            }
        }

        _positionPanel(anchor) {
            const panel = document.getElementById("epc-panel");
            if (!anchor || !panel) return;
            const rect = anchor.getBoundingClientRect();
            const gap = 10;
            const edge = 12;
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
                const detail = [c.department, c.note, c.user_type].filter(Boolean).join(" · ");
                identity.innerHTML = `<span class="epc-contact-name">${this._escape(c.name)}</span>` +
                    `<span class="epc-contact-type">${this._escape(detail || "Employee")}</span>`;
                const callBtn = document.createElement("button");
                callBtn.textContent = this.currentUuid && this._addingPeople ? "Add" : "Call";
                callBtn.className = "epc-btn epc-btn-small";
                callBtn.addEventListener("click", () => this.currentUuid && this._addingPeople ? this._addParticipant(c.user_id) : this._startCall(c.user_id));
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
            } else if (evt.event === "participant_left" && evt.uuid === this.currentUuid) {
                this._removePeer(Number(evt.payload.user_id || 0));
            } else if (["rejected", "ended", "cancelled"].includes(evt.event) && evt.uuid === this.currentUuid) {
                if (evt.event === "ended") this._teardown();
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

        async _addParticipant(userId) {
            if (!this.currentUuid) return;
            const res = await rpc("/employee_portal/call/add_participants", {uuid: this.currentUuid, user_ids: [userId]});
            if (res && res.added && res.added.length) {
                const c = this.contacts.find(x => Number(x.user_id) === Number(userId));
                if (c) this.peerNames.set(Number(userId), c.name);
                document.querySelector("#epc-active .epc-active-status").textContent = `Invited ${c ? c.name : "employee"}…`;
            }
            this._addingPeople = false;
            document.querySelector("#epc-panel .epc-panel-header span").textContent = "Call an employee";
            document.getElementById("epc-panel").classList.add("epc-hidden");
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
        }

        async _rejectIncoming() {
            if (!this.currentUuid) return;
            this._stopRinging();
            this._closeNotification();
            await rpc("/employee_portal/call/reject", { uuid: this.currentUuid });
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
        }

        async _hangup() {
            if (this.currentUuid) {
                await rpc("/employee_portal/call/end", { uuid: this.currentUuid });
            }
            this._teardown();
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
        }

        _teardown() {
            this._stopRinging();
            this._closeNotification();
            this._stopCallTimer();
            if (this.pc) {
                this.pc.close();
                this.pc = null; // legacy alias for first peer
            this.peerConnections = new Map();
            this.peerNames = new Map();
            }
            if (this.localStream) {
                this.localStream.getTracks().forEach((t) => t.stop());
                this.localStream = null;
            }
            const remoteVideo = document.getElementById("epc-remote-video");
            const localVideo = document.getElementById("epc-local-video");
            if (remoteVideo) remoteVideo.srcObject = null;
            if (localVideo) localVideo.srcObject = null;
            document.getElementById("epc-active").classList.add("epc-hidden");
            document.getElementById("epc-incoming").classList.add("epc-hidden");
            this.currentUuid = null;
            this.currentPeerName = "";
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
            pc.ontrack = (ev) => {
                let audio = document.getElementById(`epc-remote-${peerId}`);
                if (!audio) { audio = document.createElement("audio"); audio.id = `epc-remote-${peerId}`; audio.autoplay = true; audio.style.display = "none"; document.getElementById("epc-active").appendChild(audio); }
                audio.srcObject = ev.streams[0];
                const status = document.querySelector("#epc-active .epc-active-status");
                if (status) status.textContent = `${this.peerConnections.size + 1} people in meeting`;
                if (!this.callStartedAt) this._startCallTimer();
            };
            pc.onicecandidate = (ev) => { if (ev.candidate) rpc("/employee_portal/call/signal", {uuid:this.currentUuid, signal_type:"ice", data:{...ev.candidate.toJSON(), _target_user_id:peerId}}); };
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
                await pc.setRemoteDescription(new RTCSessionDescription(data));
                const answer = await pc.createAnswer(); await pc.setLocalDescription(answer);
                await rpc("/employee_portal/call/signal", {uuid:this.currentUuid, signal_type:"answer", data:{type:answer.type, sdp:answer.sdp, _target_user_id:peerId}});
            } else if (signal_type === "answer") {
                await pc.setRemoteDescription(new RTCSessionDescription(data));
            } else if (signal_type === "ice") {
                try { await pc.addIceCandidate(new RTCIceCandidate(data)); } catch (e) {}
            }
        }

        _removePeer(peerId) {
            const pc = this.peerConnections.get(peerId); if (pc) pc.close();
            this.peerConnections.delete(peerId);
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
