/**
 * IBVAP Tactical Patrol Intercept & HQ Mobilization Controller.
 * Handles transient biometric memory recurrent sightings, 1-click patrol dispatch,
 * DEFCON-1 mass infiltration pulsing banner, and allied force high-alert broadcasts.
 */

window.IBVAP_Patrol = {
  activeDefconThreat: null,
  currentEncounters: [],
  bannerDismissed: false,

  init() {
    this.bindEvents();
    this.loadRecurrentEncounters();
    this.loadMobilizationOrders();

    // Auto-refresh recurrent sightings periodically
    setInterval(() => {
      this.loadRecurrentEncounters();
    }, 10000);
  },

  bindEvents() {
    // Recurrent refresh button & filter toggle
    const btnRefresh = document.getElementById("btn-refresh-recurrent");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => this.loadRecurrentEncounters());
    }

    const chkShowAll = document.getElementById("chk-show-all-sightings");
    if (chkShowAll) {
      chkShowAll.addEventListener("change", () => this.loadRecurrentEncounters());
    }

    // DEFCON-1 Banner actions
    const btnDefconHq = document.getElementById("btn-defcon-hq");
    if (btnDefconHq) {
      btnDefconHq.addEventListener("click", () => {
        const persons = document.getElementById("defcon-person-count")?.textContent || "16";
        const vehicles = document.getElementById("defcon-vehicle-count")?.textContent || "0";
        this.openHqModal(parseInt(persons), parseInt(vehicles), "MASS INFILTRATION DETECTED IN SECTOR");
      });
    }

    const btnDefconAllies = document.getElementById("btn-defcon-allies");
    if (btnDefconAllies) {
      btnDefconAllies.addEventListener("click", () => this.openAlliesModal());
    }

    const btnDefconDismiss = document.getElementById("btn-defcon-dismiss");
    if (btnDefconDismiss) {
      btnDefconDismiss.addEventListener("click", () => {
        this.bannerDismissed = true;
        const banner = document.getElementById("defcon-banner");
        if (banner) banner.style.display = "none";
      });
    }

    // Manual mobilization buttons in tab
    const btnManualHq = document.getElementById("btn-trigger-hq-manual");
    if (btnManualHq) {
      btnManualHq.addEventListener("click", () => this.openHqModal(16, 0, "Preemptive tactical reinforcement request"));
    }

    const btnManualAllies = document.getElementById("btn-trigger-allies-manual");
    if (btnManualAllies) {
      btnManualAllies.addEventListener("click", () => this.openAlliesModal());
    }

    // Direct Reference UI Buttons
    document.getElementById("btn-dispatch-team-bravo")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-dispatch-team-bravo");
      if (btn) btn.disabled = true;
      try {
        const res = await fetch("/api/patrol/dispatch", {
          method: "POST",
          headers: { ...window.IBVAP.getAuthHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({
            patrol_unit_id: "QRT-TEAM-BRAVO (BOAT #14)",
            encounter_id: "SUBJECT-4E57",
            notes: "Immediate riverine intercept ordered for Subject-4E57 at Ichamati River Reach."
          })
        });
        const data = await res.json();
        window.IBVAP?.showToast?.(
          "QRT Team Bravo (Patrol Boat #14) dispatched to intercept at Ichamati River. SHA-256 seal logged to audit.",
          "PATROL INTERCEPT DISPATCHED"
        );
        window.IBVAP_Forensics?.loadAuditTrail?.();
      } catch (e) {
        console.error("Dispatch error:", e);
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("btn-call-reinforcements-142")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-call-reinforcements-142");
      if (btn) btn.disabled = true;
      try {
        const res = await fetch("/api/hq/reinforcements", {
          method: "POST",
          headers: { ...window.IBVAP.getAuthHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({
            sector_code: "INDO_BANGLADESH_BORDER",
            reason: "MASS_PERSONNEL_INFILTRATION",
            person_count: 16,
            vehicle_count: 0,
            details: { sector: "BOP Petrapole Pillar 142/3-S", threat: "16+ Personnel Breach" }
          })
        });
        const data = await res.json();
        window.IBVAP?.showToast?.(
          `Tactical Reinforcement Order ${data.order_id} transmitted to 142 BSF Battalion (ETA: 12 mins).`,
          "🚨 HQ REINFORCEMENTS DISPATCHED"
        );
        window.IBVAP_Forensics?.loadAuditTrail?.();
      } catch (e) {
        console.error("HQ Reinforcement error:", e);
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("btn-allied-broadcast-assam")?.addEventListener("click", async () => {
      const btn = document.getElementById("btn-allied-broadcast-assam");
      if (btn) btn.disabled = true;
      try {
        const res = await fetch("/api/allies/broadcast-alert", {
          method: "POST",
          headers: { ...window.IBVAP.getAuthHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({
            sector_code: "INDO_BANGLADESH_BORDER",
            alert_level: "DEFCON-1 (RED ALERT)",
            allied_forces: ["BORDER SECURITY FORCE", "ASSAM RIFLES", "INDIAN COAST GUARD"],
            notes: "Mass infiltration detected along Sector 88 border corridor."
          })
        });
        const data = await res.json();
        window.IBVAP?.showToast?.(
          "DEFCON-1 High Alert broadcasted to Assam Rifles, BSF Battalions & Coast Guard.",
          "📡 ALLIED FORCES ALERTED"
        );
        window.IBVAP_Forensics?.loadAuditTrail?.();
      } catch (e) {
        console.error("Allied broadcast error:", e);
      } finally {
        if (btn) btn.disabled = false;
      }
    });

    document.getElementById("btn-defcon-badge")?.addEventListener("click", () => {
      const tabDefcon = document.querySelector('.dock-tab-btn[data-tab="tab-recurrent"]');
      tabDefcon?.click();
      window.IBVAP?.showToast?.("DEFCON-1: Active mass infiltration contingency active.", "TACTICAL DEFCON STATUS");
    });

    // Quick Patrol Report from live video feed
    const btnQuickPatrol = document.getElementById("btn-quick-patrol-report");
    if (btnQuickPatrol) {
      btnQuickPatrol.addEventListener("click", () => this.openPatrolModalFromCurrentFeed());
    }

    // Modal Close buttons
    const btnClosePatrol = document.getElementById("btn-close-patrol-modal");
    if (btnClosePatrol) {
      btnClosePatrol.addEventListener("click", () => {
        document.getElementById("modal-patrol-dispatch").style.display = "none";
      });
    }

    const btnCloseHq = document.getElementById("btn-close-hq-modal");
    if (btnCloseHq) {
      btnCloseHq.addEventListener("click", () => {
        document.getElementById("modal-hq-mobilization").style.display = "none";
      });
    }

    const btnCloseAllies = document.getElementById("btn-close-allies-modal");
    if (btnCloseAllies) {
      btnCloseAllies.addEventListener("click", () => {
        document.getElementById("modal-allied-broadcast").style.display = "none";
      });
    }

    // Form Submissions
    const formPatrol = document.getElementById("form-patrol-dispatch");
    if (formPatrol) {
      formPatrol.addEventListener("submit", (e) => this.handlePatrolSubmit(e));
    }

    const formHq = document.getElementById("form-hq-mobilization");
    if (formHq) {
      formHq.addEventListener("submit", (e) => this.handleHqSubmit(e));
    }

    const formAllies = document.getElementById("form-allied-broadcast");
    if (formAllies) {
      formAllies.addEventListener("submit", (e) => this.handleAlliedSubmit(e));
    }
  },

  async loadRecurrentEncounters() {
    try {
      const chkShowAll = document.getElementById("chk-show-all-sightings");
      const showAll = chkShowAll ? chkShowAll.checked : false;

      const token = window.IBVAP?.authToken || localStorage.getItem("ibvap_token");
      const headers = token ? { "Authorization": `Bearer ${token}` } : {};

      const res = await fetch(`/api/encounters/recurrent?all=${showAll}`, { headers });
      if (!res.ok) return;

      const encounters = await res.json();
      this.currentEncounters = encounters;
      this.renderRecurrentCards(encounters);

      const countBadge = document.getElementById("recurrent-target-count");
      if (countBadge) {
        const recurrentCount = encounters.filter(e => e.sighting_count > 1).length;
        countBadge.textContent = recurrentCount;
      }
    } catch (err) {
      console.error("[IBVAP] Failed to load recurrent encounters:", err);
    }
  },

  renderRecurrentCards(encounters) {
    const container = document.getElementById("recurrent-list-container");
    if (!container) return;

    if (!encounters || encounters.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: 20px;">
          <p>NO RECURRENT TARGETS DETECTED YET</p>
          <span class="subtext">Persons appearing multiple times across outposts or over time will appear here with first/last seen locations</span>
        </div>
      `;
      return;
    }

    container.innerHTML = encounters.map(enc => {
      const isCross = (enc.first_seen_camera_id !== enc.last_seen_camera_id);
      const isRecurrent = (enc.sighting_count > 1);
      const timeDeltaStr = this.formatSeconds(enc.time_delta_seconds || 0);

      const firstTime = enc.first_seen_timestamp ? new Date(enc.first_seen_timestamp).toLocaleTimeString("en-IN") : "--:--";
      const lastTime = enc.last_seen_timestamp ? new Date(enc.last_seen_timestamp).toLocaleTimeString("en-IN") : "--:--";

      const defaultBioPhoto = "/frontend/assets/placeholder_face.jpg";
      const photoSrc = enc.snapshot_path || defaultBioPhoto;

      return `
        <div class="recurrent-card ${isCross ? 'cross-post' : ''}" id="card-enc-${enc.id}">
          <div style="position:relative; width:76px; height:90px; flex-shrink:0;">
            <img src="${photoSrc}" class="recurrent-photo" style="width:100%; height:100%; object-fit:cover; border-radius:4px; border:1px solid #1e293b;" alt="${enc.subject_alias}" onerror="this.onerror=null; this.src='${defaultBioPhoto}';">
            <span style="position:absolute; bottom:2px; left:2px; right:2px; background:rgba(0,0,0,0.75); color:#00d4ff; font-size:8px; font-family:var(--font-mono); text-align:center; border-radius:2px;">512-D CROP</span>
          </div>
          <div class="recurrent-info">
            <div class="recurrent-header">
              <span class="recurrent-alias">${enc.subject_alias}</span>
              <span class="sighting-badge ${enc.sighting_count >= 3 ? 'high-freq' : ''}">
                ${enc.sighting_count} SIGHTING${enc.sighting_count > 1 ? 'S' : ''}
              </span>
            </div>

            <div class="recurrent-trajectory">
              <div class="trajectory-step">
                <span>📍 First: <strong>${enc.first_seen_camera_id}</strong> (${firstTime})</span>
              </div>
              <div class="trajectory-step">
                <span>🎯 Last: <strong style="color:var(--accent-cyan);">${enc.last_seen_camera_id}</strong> (${lastTime})</span>
              </div>
              ${isCross ? '<div style="color:var(--accent-crimson); font-weight:600; font-size:10px; margin-top:2px;">⚠️ CROSS-OUTPOST MOVEMENT DETECTED</div>' : ''}
            </div>

            <div>
              <span class="time-delta-pill">⏱ ELAPSED: +${timeDeltaStr}</span>
            </div>

            ${enc.patrol_dispatched ? `
              <div class="dispatched-tag">✓ PATROL DISPATCHED (${enc.patrol_dispatch_notes || 'Assigned'})</div>
            ` : `
              <button class="btn-patrol-dispatch" onclick="window.IBVAP_Patrol.openPatrolModalById('${enc.id}')">
                🚨 DISPATCH PATROL INTERCEPT
              </button>
            `}
          </div>
        </div>
      `;
    }).join("");
  },

  formatSeconds(sec) {
    if (sec < 60) return `${Math.round(sec)}s`;
    const mins = Math.floor(sec / 60);
    const remSec = Math.round(sec % 60);
    if (mins < 60) return `${mins}m ${remSec}s`;
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hours}h ${remMins}m`;
  },

  openPatrolModalById(encounterId) {
    const enc = this.currentEncounters.find(e => e.id === encounterId);
    if (!enc) return;

    document.getElementById("dispatch-encounter-id").value = enc.id;
    document.getElementById("patrol-modal-alias").textContent = enc.subject_alias;
    document.getElementById("patrol-modal-count").textContent = `${enc.sighting_count} times`;
    document.getElementById("patrol-modal-first-seen").textContent = enc.first_seen_camera_id;
    document.getElementById("patrol-modal-last-seen").textContent = enc.last_seen_camera_id;
    document.getElementById("patrol-modal-delta").textContent = `+${this.formatSeconds(enc.time_delta_seconds || 0)} elapsed`;

    const img = document.getElementById("patrol-modal-photo");
    if (img) img.src = enc.snapshot_path;

    const notes = document.getElementById("dispatch-notes");
    if (notes) {
      notes.value = `Intercept and conduct identification check on recurrent subject ${enc.subject_alias}. Last spotted at ${enc.last_seen_camera_id}.`;
    }

    document.getElementById("modal-patrol-dispatch").style.display = "flex";
  },

  openPatrolModalFromCurrentFeed() {
    const camId = window.IBVAP?.activeCameraId || "CAM-01-IBB-PETRAPOLE";
    const camNames = {
      "CAM-01-IBB-PETRAPOLE": "Tower 7A - Zero Line Perimeter (Petrapole)",
      "CAM-02-IBB-ICHAMATI": "Thermal Ambush - Ichamati River Gap",
      "CAM-03-IBB-ICP-ANPR": "ICP Barrier Gate - Cargo Checkpost",
      "CAM-04-IBB-DAWKI": "IR Smart Fence - Dawki River Gorge"
    };
    const friendlyName = camNames[camId] || camId;

    document.getElementById("dispatch-encounter-id").value = "";
    document.getElementById("patrol-modal-alias").textContent = `LIVE INCIDENT // ${camId}`;
    document.getElementById("patrol-modal-count").textContent = `1 sighting (Real-Time CCTV Stream)`;
    document.getElementById("patrol-modal-first-seen").textContent = friendlyName;
    document.getElementById("patrol-modal-last-seen").textContent = friendlyName;
    document.getElementById("patrol-modal-delta").textContent = `LIVE REAL-TIME INGESTION`;

    const canvas = document.getElementById("live-canvas");
    const img = document.getElementById("patrol-modal-photo");
    if (img) {
      try {
        if (canvas) img.src = canvas.toDataURL("image/jpeg", 0.65);
        else img.src = "/frontend/assets/placeholder.jpg";
      } catch (e) {
        img.src = "/frontend/assets/placeholder.jpg";
      }
    }

    const notes = document.getElementById("dispatch-notes");
    if (notes) {
      notes.value = `Urgent ground patrol response: Suspicious movement / breach activity observed live at ${friendlyName}. Intercept and verify identification immediately.`;
    }

    document.getElementById("modal-patrol-dispatch").style.display = "flex";
  },

  openPatrolModalFromAlert(alert) {
    if (!alert) return;
    const camId = alert.camera_name || alert.camera_id || "CAM-01-IBB-PETRAPOLE";

    document.getElementById("dispatch-encounter-id").value = "";
    document.getElementById("patrol-modal-alias").textContent = `BREACH INCIDENT [${alert.id}]`;
    document.getElementById("patrol-modal-count").textContent = `ALERT: ${alert.alert_type.replace(/_/g, ' ')}`;
    document.getElementById("patrol-modal-first-seen").textContent = camId;
    document.getElementById("patrol-modal-last-seen").textContent = camId;
    document.getElementById("patrol-modal-delta").textContent = `SEVERITY: ${alert.severity}`;

    const img = document.getElementById("patrol-modal-photo");
    if (img) img.src = alert.snapshot_path || "/frontend/assets/placeholder.jpg";

    const notes = document.getElementById("dispatch-notes");
    if (notes) {
      notes.value = `Urgent intercept order: ${alert.alert_type.replace(/_/g, ' ')} detected at ${camId}. Confidence: ${(alert.confidence * 100).toFixed(0)}%. Ground QRT response required immediately.`;
    }

    document.getElementById("modal-patrol-dispatch").style.display = "flex";
  },

  async handlePatrolSubmit(e) {
    e.preventDefault();
    const encounterId = document.getElementById("dispatch-encounter-id").value;
    const patrolUnit = document.getElementById("select-patrol-unit").value;
    const notes = document.getElementById("dispatch-notes").value;
    const activeCam = window.IBVAP?.activeCameraId || "CAM-01-IBB-PETRAPOLE";

    const token = window.IBVAP?.authToken || localStorage.getItem("ibvap_token");
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {})
    };

    const payload = {
      patrol_unit_id: patrolUnit,
      notes: notes,
      camera_id: activeCam,
      subject_alias: document.getElementById("patrol-modal-alias")?.textContent || "SECTOR-INCIDENT"
    };
    if (encounterId) {
      payload.encounter_id = encounterId;
    }

    try {
      const res = await fetch("/api/patrol/dispatch", {
        method: "POST",
        headers,
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Patrol dispatch failed: ${err.detail || 'Authorization required'}`);
        return;
      }

      const data = await res.json();
      document.getElementById("modal-patrol-dispatch").style.display = "none";

      if (window.IBVAP?.showToast) {
        window.IBVAP.showToast(
          `Tactical Patrol ${patrolUnit} deployed! Report transmitted and sealed into SHA-256 audit ledger.`,
          "PATROL DISPATCHED"
        );
      }

      // Reload encounters and audit trail
      this.loadRecurrentEncounters();
      if (window.IBVAP_Forensics?.loadAuditTrail) {
        window.IBVAP_Forensics.loadAuditTrail();
      }
    } catch (err) {
      console.error("[IBVAP] Patrol dispatch error:", err);
      alert("Network error dispatching patrol.");
    }
  },

  // ---------------------------------------------------------------------------
  // DEFCON-1 MASS INFILTRATION & HQ MOBILIZATION
  // ---------------------------------------------------------------------------
  handleMassStatus(massStatus) {
    if (massStatus.is_threat && !this.bannerDismissed) {
      this.showDefconBanner(massStatus);
    }
  },

  triggerDefcon1Alert(threatData) {
    this.bannerDismissed = false;
    this.showDefconBanner(threatData);

    if (window.IBVAP?.playAlarmSound) {
      window.IBVAP.playAlarmSound("CRITICAL");
    }

    if (window.IBVAP?.showToast) {
      window.IBVAP.showToast(
        threatData.message || "MASS INFILTRATION DETECTED: >=15 personnel active across border corridor!",
        "DEFCON-1 RED ALERT"
      );
    }
  },

  showDefconBanner(data) {
    const banner = document.getElementById("defcon-banner");
    if (!banner) return;

    banner.style.display = "block";

    const msgEl = document.getElementById("defcon-message");
    if (msgEl && data.message) msgEl.textContent = data.message;

    const pCountEl = document.getElementById("defcon-person-count");
    if (pCountEl) pCountEl.textContent = data.person_count || 0;

    const vCountEl = document.getElementById("defcon-vehicle-count");
    if (vCountEl) vCountEl.textContent = data.vehicle_count || 0;
  },

  openHqModal(persons = 16, vehicles = 0, reason = "") {
    const pInput = document.getElementById("hq-person-count");
    if (pInput) pInput.value = persons;

    const vInput = document.getElementById("hq-vehicle-count");
    if (vInput) vInput.value = vehicles;

    const rInput = document.getElementById("hq-escalation-reason");
    if (rInput && reason) rInput.value = reason;

    document.getElementById("modal-hq-mobilization").style.display = "flex";
  },

  openAlliesModal() {
    document.getElementById("modal-allied-broadcast").style.display = "flex";
  },

  async handleHqSubmit(e) {
    e.preventDefault();
    const persons = parseInt(document.getElementById("hq-person-count").value || 0);
    const vehicles = parseInt(document.getElementById("hq-vehicle-count").value || 0);
    const reason = document.getElementById("hq-escalation-reason").value;
    const autoAllies = document.getElementById("hq-auto-allied-alert")?.checked;

    const token = window.IBVAP?.authToken || localStorage.getItem("ibvap_token");
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {})
    };

    try {
      const res = await fetch("/api/hq/reinforcements", {
        method: "POST",
        headers,
        body: JSON.stringify({
          sector_code: "INDO_BANGLADESH_BORDER",
          reason: reason,
          person_count: persons,
          vehicle_count: vehicles,
          details: {
            tactical_assessment: "Emergency perimeter reinforcement required immediately."
          }
        })
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`HQ Mobilization failed: ${err.detail || 'Access denied'}`);
        return;
      }

      const data = await res.json();

      // If auto-allies is checked, also send Allied warning
      if (autoAllies) {
        await fetch("/api/allies/broadcast-alert", {
          method: "POST",
          headers,
          body: JSON.stringify({
            mobilization_id: data.order_id,
            sector_code: "INDO_BANGLADESH_BORDER",
            alert_level: "DEFCON-1 (RED ALERT)",
            notes: `High alert dispatched following HQ Mobilization Order ${data.order_id}`
          })
        });
      }

      document.getElementById("modal-hq-mobilization").style.display = "none";

      if (window.IBVAP?.showToast) {
        window.IBVAP.showToast(
          `Mobilization Order ${data.order_id} transmitted to Sector HQ! Transmission Hash: ${data.transmission_hash.substring(0, 16)}... ETA: ${data.eta_minutes} mins`,
          "HQ REINFORCEMENTS MOBILIZED"
        );
      }

      this.loadMobilizationOrders();
      if (window.IBVAP_Forensics?.loadAuditTrail) {
        window.IBVAP_Forensics.loadAuditTrail();
      }
    } catch (err) {
      console.error("[IBVAP] HQ mobilization error:", err);
      alert("Network error transmitting order to Sector HQ.");
    }
  },

  async handleAlliedSubmit(e) {
    e.preventDefault();
    const notes = document.getElementById("allied-alert-notes").value;

    const token = window.IBVAP?.authToken || localStorage.getItem("ibvap_token");
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { "Authorization": `Bearer ${token}` } : {})
    };

    try {
      const res = await fetch("/api/allies/broadcast-alert", {
        method: "POST",
        headers,
        body: JSON.stringify({
          sector_code: "INDO_BANGLADESH_BORDER",
          alert_level: "DEFCON-1 (RED ALERT)",
          notes: notes
        })
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Allied broadcast failed: ${err.detail || 'Access denied'}`);
        return;
      }

      const data = await res.json();
      document.getElementById("modal-allied-broadcast").style.display = "none";

      if (window.IBVAP?.showToast) {
        window.IBVAP.showToast(
          `DEFCON-1 High Alert broadcasted to BSF, Assam Rifles, Coast Guard & Local Police!`,
          "ALLIED HIGH ALERT ACTIVE"
        );
      }

      this.loadMobilizationOrders();
      if (window.IBVAP_Forensics?.loadAuditTrail) {
        window.IBVAP_Forensics.loadAuditTrail();
      }
    } catch (err) {
      console.error("[IBVAP] Allied broadcast error:", err);
      alert("Network error broadcasting allied alert.");
    }
  },

  async loadMobilizationOrders() {
    try {
      const res = await fetch("/api/hq/mobilizations");
      if (!res.ok) return;

      const orders = await res.json();
      const countBadge = document.getElementById("mob-orders-count");
      if (countBadge) countBadge.textContent = orders.length;

      const tbody = document.getElementById("tbody-mobilization");
      if (!tbody) return;

      if (!orders || orders.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#8493a8;">No emergency mobilization orders active</td></tr>`;
        return;
      }

      tbody.innerHTML = orders.map(ord => {
        const timeStr = ord.timestamp ? new Date(ord.timestamp).toLocaleString("en-IN") : "--";
        const shortHash = ord.hq_transmission_hash ? `${ord.hq_transmission_hash.substring(0, 16)}...` : "--";

        return `
          <tr>
            <td><strong style="color:#fff;">${ord.id}</strong></td>
            <td class="font-mono">${timeStr}</td>
            <td><span style="color:var(--accent-crimson); font-weight:700;">${ord.trigger_reason}</span></td>
            <td><strong style="color:var(--accent-amber);">${ord.person_count} P</strong> / <strong style="color:var(--accent-cyan);">${ord.vehicle_count} V</strong></td>
            <td><span style="color:var(--accent-emerald); font-weight:600;">${ord.status}</span></td>
            <td>${ord.allied_alert_broadcast ? '<span style="color:var(--accent-emerald); font-weight:700;">✓ BROADCASTED</span>' : '<span style="color:#8493a8;">NONE</span>'}</td>
            <td><span class="mob-hash-badge" title="${ord.hq_transmission_hash}">${shortHash}</span></td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("[IBVAP] Failed to load mobilization orders:", err);
    }
  },

  handleRecurrentSighting(data) {
    // Immediate reload of recurrent encounters
    this.loadRecurrentEncounters();

    if (window.IBVAP?.showToast && data.encounter) {
      const crossTag = data.is_cross_post ? " [TRANSITING BETWEEN OUTPOSTS]" : "";
      window.IBVAP.showToast(
        `Person ${data.encounter.subject_alias} reappeared at ${data.encounter.last_seen_camera_id}${crossTag}! (Sighting #${data.encounter.sighting_count}, Sim: ${data.similarity_score}%)`,
        "RECURRENT PERSON DETECTED"
      );
    }
  }
};

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  window.IBVAP_Patrol.init();
});
