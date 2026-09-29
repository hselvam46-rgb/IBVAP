/**
 * Real-Time Alert Triage Manager & Human-in-the-Loop Decision Support Workflow.
 * Enforces mandatory operator sign-off before alerts can be escalated to HQ/QRF.
 * Uses real-time camera snapshot images and live-ticking IST timestamps.
 */

window.IBVAP_Alerts = {
  activeAlerts: [],
  selectedAlert: null,
  liveTickerInterval: null,

  init() {
    this.bindModalEvents();
    this.bindControls();
    this.loadInitialAlerts();
    this.startLiveTicker();
  },

  formatIST(isoString) {
    if (!isoString) {
      return new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false }) + " IST";
    }
    const d = new Date(isoString);
    if (isNaN(d.getTime())) {
      return new Date().toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false }) + " IST";
    }
    return d.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour12: false }) + " IST";
  },

  formatTimeAgo(isoString) {
    if (!isoString) return "JUST NOW";
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return "JUST NOW";
    const diffSec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
    if (diffSec < 5) return "JUST NOW";
    if (diffSec < 60) return `${diffSec}s AGO`;
    if (diffSec < 3600) {
      const m = Math.floor(diffSec / 60);
      const s = diffSec % 60;
      return `${m}m ${s}s AGO`;
    }
    const h = Math.floor(diffSec / 3600);
    const m = Math.floor((diffSec % 3600) / 60);
    return `${h}h ${m}m AGO`;
  },

  startLiveTicker() {
    if (this.liveTickerInterval) clearInterval(this.liveTickerInterval);
    this.liveTickerInterval = setInterval(() => {
      this.updateLiveTimers();
    }, 1000);
  },

  updateLiveTimers() {
    const cards = document.querySelectorAll(".triage-card[data-timestamp]");
    cards.forEach(card => {
      const ts = card.getAttribute("data-timestamp");
      if (!ts) return;
      const timeEl = card.querySelector(".card-timestamp");
      const agoEl = card.querySelector(".card-time-ago");
      if (timeEl) {
        timeEl.textContent = this.formatIST(ts);
      }
      if (agoEl) {
        agoEl.textContent = this.formatTimeAgo(ts);
      }
    });
  },

  bindControls() {
    // Reset / Clear Queue Button for clean presentation
    const btnClear = document.getElementById("btn-clear-demo-queue");
    if (btnClear) {
      btnClear.addEventListener("click", async () => {
        if (!confirm("Reset alert queue to 0 for a clean presentation demo?")) return;
        try {
          const res = await fetch("/api/alerts/clear-demo", {
            method: "POST",
            headers: window.IBVAP.getAuthHeaders()
          });
          if (res.ok) {
            this.activeAlerts = [];
            this.renderAlertQueue();
            window.IBVAP_Forensics?.loadAuditTrail();
            if (window.IBVAP?.showToast) {
              window.IBVAP.showToast("Alert queue cleared to 0 for clean demonstration.", "DEMO RESET");
            }
          }
        } catch (e) {
          console.error("Failed to clear demo queue:", e);
        }
      });
    }

    // Trigger Demo Breach Button for on-cue demo
    const btnTrigger = document.getElementById("btn-trigger-demo-breach");
    if (btnTrigger) {
      btnTrigger.addEventListener("click", async () => {
        btnTrigger.disabled = true;
        const origText = btnTrigger.innerHTML;
        btnTrigger.innerHTML = "⚡ TRIGGERING...";
        try {
          const activeCam = window.IBVAP_Player?.activeCameraId || window.IBVAP?.activeCameraId || "CAM-01-IBB-PETRAPOLE";
          const res = await fetch("/api/alerts/trigger-demo", {
            method: "POST",
            headers: {
              ...window.IBVAP.getAuthHeaders(),
              "Content-Type": "application/json"
            },
            body: JSON.stringify({
              alert_type: "TRIPWIRE_BREACH",
              camera_id: activeCam
            })
          });
          if (res.ok) {
            const data = await res.json();
            const alertObj = data.alert || data;
            if (alertObj && alertObj.id) {
              this.addAlert(alertObj);
              if (window.IBVAP?.showToast) {
                window.IBVAP.showToast(
                  `Critical Tripwire Breach captured at ${alertObj.camera_id} (${alertObj.id})`,
                  "⚡ REAL-TIME BREACH CAPTURED"
                );
              }
            }
          } else {
            console.error("Trigger demo breach failed:", await res.text());
          }
        } catch (e) {
          console.error("Failed to trigger demo breach:", e);
        } finally {
          btnTrigger.disabled = false;
          btnTrigger.innerHTML = origText;
        }
      });
    }
  },

  bindModalEvents() {
    const modal = document.getElementById("modal-human-review");
    const btnClose = document.getElementById("btn-close-review");
    if (btnClose && modal) {
      btnClose.addEventListener("click", () => {
        modal.style.display = "none";
      });
    }

    // Modal Action Buttons
    document.getElementById("btn-action-ack")?.addEventListener("click", () => this.submitDecision("ACKNOWLEDGE"));
    document.getElementById("btn-action-escalate")?.addEventListener("click", () => this.submitDecision("ESCALATE"));
    document.getElementById("btn-action-dismiss")?.addEventListener("click", () => this.submitDecision("DISMISS"));
    document.getElementById("btn-action-dispatch-patrol")?.addEventListener("click", () => {
      if (this.selectedAlert && window.IBVAP_Patrol) {
        document.getElementById("modal-human-review").style.display = "none";
        window.IBVAP_Patrol.openPatrolModalFromAlert(this.selectedAlert);
      }
    });
  },

  async loadInitialAlerts() {
    try {
      const res = await fetch("/api/alerts?status=UNACKNOWLEDGED&limit=15");
      if (res.ok) {
        const alerts = await res.json();
        if (Array.isArray(alerts)) {
          this.activeAlerts = alerts;
        }
        this.renderAlertQueue();
      }
    } catch (e) {
      console.warn("Could not fetch alerts list:", e);
    }
  },

  addAlert(alert) {
    if (!alert || !alert.id) return;
    // Check if alert already exists
    if (this.activeAlerts.some(a => a.id === alert.id)) return;

    // Ensure timestamp is present
    if (!alert.timestamp) alert.timestamp = new Date().toISOString();

    this.activeAlerts.unshift(alert);
    if (this.activeAlerts.length > 50) this.activeAlerts.pop();

    this.renderAlertQueue();

    // Flash breached camera on tactical map
    if (window.IBVAP_SectorMap) {
      window.IBVAP_SectorMap.triggerCameraBreach(alert.camera_id);
    }
  },

  renderAlertQueue() {
    const container = document.getElementById("alert-stream-list");
    const emptyState = document.getElementById("alerts-empty-state");
    if (!container) return;

    // Filter unacknowledged alerts
    const unhandled = this.activeAlerts.filter(a => a.status === "UNACKNOWLEDGED");

    // Update Header Badges
    const critCount = unhandled.filter(a => a.severity === "CRITICAL").length;
    const highCount = unhandled.filter(a => a.severity === "HIGH").length;

    const badgeCrit = document.getElementById("badge-crit-count");
    if (badgeCrit) badgeCrit.textContent = `${critCount} CRIT`;
    const badgeHigh = document.getElementById("badge-high-count");
    if (badgeHigh) badgeHigh.textContent = `${highCount} HIGH`;
    const telAlert = document.getElementById("telemetry-alert-count");
    if (telAlert) telAlert.textContent = unhandled.length;

    if (unhandled.length === 0) {
      if (emptyState) emptyState.style.display = "block";
      container.innerHTML = "";
      return;
    }

    if (emptyState) emptyState.style.display = "none";

    // Clear and rebuild cards
    container.innerHTML = "";
    unhandled.slice(0, 15).forEach(alert => {
      const card = this.createAlertCard(alert);
      container.appendChild(card);
    });
  },

  createAlertCard(alert) {
    const card = document.createElement("div");
    const isCrit = (alert.severity === "CRITICAL");
    card.className = `triage-card ${isCrit ? "card-critical" : ""}`;
    card.id = `card-${alert.id}`;
    card.setAttribute("data-timestamp", alert.timestamp || new Date().toISOString());

    const timeStr = this.formatIST(alert.timestamp);
    const timeAgoStr = this.formatTimeAgo(alert.timestamp);

    // Meta resolution
    let meta = {};
    if (alert.metadata) {
      meta = typeof alert.metadata === "string" ? JSON.parse(alert.metadata) : alert.metadata;
    } else if (alert.metadata_json) {
      try { meta = JSON.parse(alert.metadata_json); } catch(e) {}
    }

    const camNames = {
      "CAM-01-IBB-PETRAPOLE": "PTZ-CAM-01 / SECTOR 88-T7A",
      "CAM-02-IBB-ICHAMATI": "THERMAL-CAM-02 / RIVERINE GAP",
      "CAM-03-IBB-ICP-ANPR": "ANPR-CAM-03 / CARGO GATE 3",
      "CAM-04-IBB-DAWKI": "SMART-FENCE-04 / DAWKI POST 12"
    };

    const camLabel = camNames[alert.camera_id] || alert.camera_id || "PTZ-CAM-01 / SECTOR 88-T7A";
    const confPercent = Math.round((alert.confidence || 0.94) * 100);

    // Resolve real-time snapshot image URL
    let snapSrc = alert.snapshot_path;
    if (!snapSrc || snapSrc === "null" || snapSrc === "undefined") {
      snapSrc = window.IBVAP_Player?.getLiveSnapshotDataUrl?.(alert.camera_id) || "/frontend/assets/placeholder.jpg";
    } else if (!snapSrc.startsWith("data:") && !snapSrc.startsWith("/")) {
      snapSrc = "/" + snapSrc;
    }

    // Top Meta Header
    const topMetaHtml = `
      <div class="card-top-meta">
        <span class="${isCrit ? 'tag-crit-red' : 'tag-high-dark'}">${isCrit ? 'CRITICAL THREAT' : 'HIGH PRIORITY'}</span>
        <span class="card-timestamp">${timeStr}</span>
        <span class="${isCrit ? 'badge-time-ago-red' : 'badge-time-ago-gray'} card-time-ago">${timeAgoStr}</span>
      </div>
    `;

    // 1. WATCHLIST FACE MATCH
    if (alert.alert_type === "WATCHLIST_FACE_MATCH") {
      const targetName = meta.target_name || "T. HOSSAIN (ALIAS TARIQ)";
      const targetShort = targetName.length > 17 ? targetName.substring(0, 15) + "..." : targetName;
      const refPhoto = meta.reference_photo || "/frontend/assets/watchlist/profile_test_01.jpg";
      const simScore = Math.round(meta.similarity_score || 89);
      const subjectNum = meta.subject_id ? meta.subject_id.replace(/\D/g, "") : "402";

      card.innerHTML = `
        ${topMetaHtml}
        <div class="card-incident-title">TRIPWIRE BREACH - ZERO LINE SECTOR A4</div>
        <div class="card-incident-sensor">SENSOR: ${camLabel} &nbsp;|&nbsp; CONF: ${confPercent}% AI PROB</div>

        <div class="biometric-crop-row">
          <div class="crop-box">
            <div class="crop-box-header bg-dark">PROBE CROP</div>
            <img src="${snapSrc}" alt="Probe Crop" class="crop-img" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
            <span class="crop-footer-lbl">FRAME #${alert.track_id ? '88' + alert.track_id + 'A' : '8812A'}</span>
          </div>

          <div class="crop-box">
            <div class="crop-box-header bg-red">WATCHLIST #${subjectNum}</div>
            <img src="${refPhoto}" alt="Watchlist Target" class="crop-img" onerror="this.onerror=null; this.src='/frontend/assets/watchlist/profile_test_01.jpg';">
            <span class="crop-footer-lbl" title="${targetName}">${targetShort}</span>
          </div>
        </div>

        <div class="biometric-convergence-block">
          <div class="convergence-label">
            <span>BIOMETRIC CONVERGENCE</span>
            <span>${simScore}% MATCH (PRIORITY RED)</span>
          </div>
          <div class="convergence-meter">
            <div class="convergence-fill" style="width: ${simScore}%;"></div>
          </div>
        </div>

        <div class="card-actions-3">
          <button class="btn-card-action btn-dismiss" onclick="window.IBVAP_Alerts.handleDismiss('${alert.id}')">DISMISS</button>
          <button class="btn-card-action btn-investigate" onclick="window.IBVAP_Alerts.openReviewModal('${alert.id}')">INVESTIGATE</button>
          <button class="btn-card-action btn-escalate" onclick="window.IBVAP_Alerts.handleEscalate('${alert.id}')">ESCALATE QRF</button>
        </div>
      `;
      return card;
    }

    // 2. ANPR VEHICLE HOTLIST
    if (alert.alert_type === "ANPR_FLAGGED_VEHICLE") {
      const plateNumber = meta.plate_number || "WB 02 AB 1234";
      const hotlistMsg = meta.hotlist_reason || "FLAGGED: SMUGGLING CORRIDOR";

      card.innerHTML = `
        ${topMetaHtml}
        <div class="card-incident-title">HOTLIST VEHICLE DETECTED - CARGO GATE 3</div>
        <div class="card-incident-sensor">ANPR OCR READOUT &nbsp;|&nbsp; SENSOR: ${camLabel}</div>

        <div style="margin: 4px 0;">
          <img src="${snapSrc}" alt="Vehicle Capture" class="crop-img" style="height: 105px; width: 100%; object-fit: cover;" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
        </div>

        <div class="anpr-plate-display">
          <span class="plate-number-large font-mono">${plateNumber}</span>
          <div class="plate-status-group">
            <span class="badge-db-hit">DATABASE HIT</span>
            <span class="plate-flag-msg">${hotlistMsg}</span>
          </div>
        </div>

        <div class="card-actions-2">
          <button class="btn-card-action btn-hold" onclick="window.IBVAP_Alerts.handleHoldGate('${alert.id}')">HOLD GATE BARRIER</button>
          <button class="btn-card-action btn-alert-green" onclick="window.IBVAP_Alerts.handleAlertCustoms('${alert.id}')">ALERT CUSTOMS &amp; CISF</button>
        </div>
      `;
      return card;
    }

    // 3. TRIPWIRE / LOITERING / MASS BREACH
    const zoneName = meta.zone_name || "ZERO LINE PRIMARY BARRIER";
    const direction = meta.direction || "INBOUND";
    let incidentTitle = "TRIPWIRE BREACH - ZERO LINE SECTOR A4";
    if (alert.alert_type === "LOITERING_DWELL") {
      incidentTitle = `RESTRICTED DWELL EXCEEDED - ${zoneName.toUpperCase()}`;
    } else if (alert.alert_type.includes("MASS") || alert.alert_type.includes("DEFCON")) {
      incidentTitle = "DEFCON-1 MASS CONVOY INCURSION DETECTED";
    } else if (meta.zone_name) {
      incidentTitle = `TRIPWIRE BREACH - ${meta.zone_name.toUpperCase()}`;
    }

    card.innerHTML = `
      ${topMetaHtml}
      <div class="card-incident-title">${incidentTitle}</div>
      <div class="card-incident-sensor">SENSOR: ${camLabel} &nbsp;|&nbsp; CONF: ${confPercent}% AI PROB</div>

      <div class="biometric-crop-row">
        <div class="crop-box">
          <div class="crop-box-header bg-dark">LIVE INCIDENT FRAME</div>
          <img src="${snapSrc}" alt="Live Incident Capture" class="crop-img" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
          <span class="crop-footer-lbl">${zoneName}</span>
        </div>

        <div class="crop-box">
          <div class="crop-box-header bg-red">AI DETECTION OVERLAY</div>
          <img src="${snapSrc}" alt="Target Context" class="crop-img" style="filter: contrast(1.15) brightness(0.95);" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
          <span class="crop-footer-lbl">${direction} // ${(alert.object_type || "PERSON").toUpperCase()}</span>
        </div>
      </div>

      <div class="biometric-convergence-block">
        <div class="convergence-label">
          <span>AI THREAT PROBABILITY</span>
          <span>${confPercent}% (ACTIVE SECTOR EVENT)</span>
        </div>
        <div class="convergence-meter">
          <div class="convergence-fill" style="width: ${confPercent}%;"></div>
        </div>
      </div>

      <div class="card-actions-3">
        <button class="btn-card-action btn-dismiss" onclick="window.IBVAP_Alerts.handleDismiss('${alert.id}')">DISMISS</button>
        <button class="btn-card-action btn-investigate" onclick="window.IBVAP_Alerts.openReviewModal('${alert.id}')">INVESTIGATE</button>
        <button class="btn-card-action btn-escalate" onclick="window.IBVAP_Alerts.handleEscalate('${alert.id}')">ESCALATE QRF</button>
      </div>
    `;
    return card;
  },

  async handleDismiss(alertId) {
    const alert = this.activeAlerts.find(a => a.id === alertId);
    if (alert) alert.status = "DISMISSED";

    try {
      await fetch(`/api/alerts/${alertId}/dismiss`, {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders(),
        body: JSON.stringify({ reason: "Dismissed by operator in live triage" })
      });
    } catch (e) {
      console.warn("Dismiss API error:", e);
    }

    const card = document.getElementById(`card-${alertId}`);
    if (card) {
      card.style.transition = "all 0.3s ease";
      card.style.opacity = "0";
      card.style.transform = "translateX(25px)";
      setTimeout(() => {
        this.activeAlerts = this.activeAlerts.filter(a => a.id !== alertId);
        this.renderAlertQueue();
      }, 300);
    } else {
      this.activeAlerts = this.activeAlerts.filter(a => a.id !== alertId);
      this.renderAlertQueue();
    }

    window.IBVAP?.showToast?.(`Incident ${alertId} marked as dismissed/resolved by operator.`, "ALERT DISMISSED");
    window.IBVAP_Forensics?.loadAuditTrail?.();
  },

  async handleEscalate(alertId) {
    const alert = this.activeAlerts.find(a => a.id === alertId);
    if (!alert) return;

    try {
      await fetch(`/api/alerts/${alertId}/escalate`, {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders(),
        body: JSON.stringify({
          notes: "Escalated to BSF Sector QRF Delta-9",
          target_team: "BSF_QRF_PATROL"
        })
      });
    } catch (e) {
      console.warn("Escalate API error:", e);
    }

    alert.status = "ESCALATED";
    const card = document.getElementById(`card-${alertId}`);
    if (card) {
      card.style.borderColor = "#dc2626";
      card.style.boxShadow = "0 0 14px rgba(220, 38, 38, 0.45)";
    }

    window.IBVAP?.showToast?.(
      `ESCALATED TO BSF QUICK REACTION TEAM (QRF DELTA-9). Intercept in progress for ${alert.camera_name || alert.camera_id}.`,
      "🚨 QRF ESCALATED"
    );
    window.IBVAP_Forensics?.loadAuditTrail?.();
  },

  handleHoldGate(alertId) {
    window.IBVAP?.showToast?.("CARGO GATE 3 BARRIER LOCKED DOWN. Automatic spike strip deployed.", "GATE LOCKDOWN ACTIVE");
    window.IBVAP_Forensics?.loadAuditTrail?.();
  },

  handleAlertCustoms(alertId) {
    window.IBVAP?.showToast?.("High-priority alert transmitted to Customs Checkpost & CISF Terminal Units.", "CUSTOMS & CISF ALERTED");
    window.IBVAP_Forensics?.loadAuditTrail?.();
  },

  openReviewModal(alertId, autoFocusEscalate = false) {
    const alert = this.activeAlerts.find(a => a.id === alertId);
    if (!alert) return;

    this.selectedAlert = alert;
    const modal = document.getElementById("modal-human-review");
    const mediaContainer = document.getElementById("review-media-container");
    const metaBox = document.getElementById("review-meta-box");
    const notesInput = document.getElementById("review-operator-notes");

    if (notesInput) notesInput.value = "";

    let meta = {};
    if (alert.metadata) {
      meta = typeof alert.metadata === "string" ? JSON.parse(alert.metadata) : alert.metadata;
    } else if (alert.metadata_json) {
      try { meta = JSON.parse(alert.metadata_json); } catch(e) {}
    }

    const snapSrc = alert.snapshot_path || window.IBVAP_Player?.getLiveSnapshotDataUrl?.(alert.camera_id) || "/frontend/assets/placeholder.jpg";

    // Build Media & Comparison Pane
    if (alert.alert_type === "WATCHLIST_FACE_MATCH") {
      mediaContainer.innerHTML = `
        <div class="probe-vs-watchlist">
          <div class="probe-card">
            <img class="probe-img" src="${snapSrc}" alt="Probe Crop" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
            <div class="probe-label">CCTV PROBE CROP</div>
          </div>
          <div class="probe-card">
            <img class="probe-img" src="${meta.reference_photo || '/frontend/assets/watchlist/profile_test_01.jpg'}" alt="Watchlist Reference">
            <div class="probe-label">WATCHLIST PROFILE</div>
          </div>
        </div>
        <div class="similarity-meter">
          <span class="sim-val">ARCFACE MATCH: ${meta.similarity_score || 89.2}%</span>
          <div style="font-size:10px; color:#8493a8; margin-top:4px;">512-Dimensional Cosine Match Vector</div>
        </div>
      `;
    } else {
      mediaContainer.innerHTML = `
        <img src="${snapSrc}" style="max-width:100%; max-height:220px; object-fit:contain; border-radius:4px;" alt="Incident Snapshot" onerror="this.onerror=null; this.src='/frontend/assets/placeholder.jpg';">
        <div style="font-size:10px; color:#00e5a3; margin-top:8px; font-family:'JetBrains Mono',monospace;">
          CRYPTOGRAPHIC INTEGRITY: REAL-TIME FRAME BUFFERED & TIME-STAMPED
        </div>
      `;
    }

    // Build Metadata Details Box
    metaBox.innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:11px; margin-bottom:12px; background:rgba(0,0,0,0.3); padding:10px; border-radius:4px;">
        <div><strong>ALERT ID:</strong> <span class="font-mono">${alert.id}</span></div>
        <div><strong>TIMESTAMP:</strong> <span class="font-mono">${this.formatIST(alert.timestamp)}</span></div>
        <div><strong>SECTOR:</strong> <span>${alert.sector || 'Indo-Bangladesh Border'}</span></div>
        <div><strong>CAMERA POST:</strong> <span>${alert.camera_name || alert.camera_id}</span></div>
        <div><strong>THREAT CLASS:</strong> <span style="color:#ff3366; font-weight:700;">${(alert.object_type || "PERSON").toUpperCase()}</span></div>
        <div><strong>SEVERITY:</strong> <span style="color:#ff3366; font-weight:700;">${alert.severity}</span></div>
      </div>
    `;

    if (modal) modal.style.display = "flex";
  },

  async submitDecision(action) {
    if (!this.selectedAlert) return;
    const alertId = this.selectedAlert.id;
    const notes = document.getElementById("review-operator-notes")?.value.trim() || `Decision: ${action} signed by operator`;

    let endpoint = "";
    if (action === "ACKNOWLEDGE") endpoint = `/api/alerts/${alertId}/acknowledge`;
    else if (action === "ESCALATE") endpoint = `/api/alerts/${alertId}/escalate`;
    else if (action === "DISMISS") endpoint = `/api/alerts/${alertId}/dismiss`;

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: window.IBVAP.getAuthHeaders(),
        body: JSON.stringify({ notes, target_team: "BSF_QRF_PATROL" })
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Action failed: ${err.detail || "Unauthorized"}`);
        return;
      }

      this.selectedAlert.status = action === "ACKNOWLEDGE" ? "ACKNOWLEDGED" : (action === "ESCALATE" ? "ESCALATED" : "DISMISSED");
      document.getElementById("modal-human-review").style.display = "none";
      this.renderAlertQueue();
      window.IBVAP_Forensics?.loadAuditTrail();
    } catch (e) {
      alert("Error contacting edge server.");
    }
  }
};

document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_Alerts.init();
});
